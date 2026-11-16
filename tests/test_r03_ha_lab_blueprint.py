"""Offline-only security tests for approved three-host HA design."""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path
from unittest import TestCase

ROOT=Path(__file__).resolve().parents[1]
LAB=ROOT/"docs"/"verification"/"sec001-r03"/"ha-lab"


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    sys.modules[name]=module
    spec.loader.exec_module(module)
    return module

renderer=load("ha_lab_render",LAB/"render_node.py")
facts=load("ha_lab_facts",LAB/"collect_host_facts.py")
contract=load("ha_lab_contract",ROOT/"scripts"/"ci"/"r03_ha_evidence_contract.py")


def synthetic():
    data=json.loads((LAB/"inventory.example.json").read_text())
    data.update(owner_authorized=True,network_cidr="10.77.30.0/24")
    data["tls"]={"independent_ca_fingerprint_sha256":"sha256:"+"c"*64,"san_and_client_auth_verified":True}
    data["images"]={
        "postgres":"sha256:"+"1"*64,"patroni":"sha256:"+"2"*64,"etcd":"sha256:"+"3"*64,
        "patroni_image_ref":"lab.example.com/patroni@sha256:"+"2"*64,
        "etcd_image_ref":"lab.example.com/etcd@sha256:"+"3"*64,
    }
    for i,h in enumerate(data["hosts"]):
        h.update(host_id=f"synthetic-{i}",address=f"10.77.30.{11+i}",
                 failure_domain=f"synthetic-domain-{i}",physical_host=True,
                 owner_authorized=True,host_attestation_sha256="sha256:"+"a"*64)
    return data


class HALabBlueprintTests(TestCase):
    def test_unapproved_inventory_is_blocked(self):
        original=json.loads((LAB/"inventory.example.json").read_text())
        self.assertTrue(renderer.blockers(original))
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                renderer.render(original,"aptron-ha-01",Path(tmp)/"test")

    def test_synthetic_render_still_not_certification(self):
        data=synthetic()
        self.assertEqual(renderer.blockers(data),[])
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/"node"
            decision=renderer.render(data,"aptron-ha-01",out)
            self.assertEqual(decision["status"],"CONFIG_RENDERED_NOT_DEPLOYED")
            self.assertFalse(decision["release_eligible"])
            cfg=json.loads((out/"patroni.yaml").read_text())
            self.assertEqual(cfg["watchdog"]["mode"],"required")
            self.assertTrue(cfg["bootstrap"]["dcs"]["synchronous_mode_strict"])
            self.assertEqual(cfg["bootstrap"]["dcs"]["synchronous_node_count"],1)
            self.assertEqual(cfg["etcd3"]["protocol"],"https")
            self.assertEqual(cfg["restapi"]["verify_client"],"required")
            self.assertEqual(cfg["ctl"]["certfile"],"/run/lab-patroni-tls/client.crt")
            self.assertEqual(cfg["ctl"]["keyfile"],"/run/lab-patroni-tls/client.key")
            self.assertTrue(cfg["restapi"]["allowlist_include_members"])
            self.assertEqual(cfg["bootstrap"]["dcs"]["postgresql"]["parameters"]["ssl_min_protocol_version"],"TLSv1.2")
            with self.assertRaises(ValueError):
                renderer.render(data,"aptron-ha-01",out)

    def test_insufficient_sizing_is_rejected(self):
        for name,value in (("vcpus",7),("memory_gib",31),("data_disk_gib",199)):
            data=synthetic()
            data["hosts"][0][name]=value
            self.assertTrue(any(name in x for x in renderer.blockers(data)))

    def test_duplicate_domains_or_documentation_ips_block(self):
        data=synthetic()
        data["hosts"][2]["failure_domain"]=data["hosts"][1]["failure_domain"]
        self.assertTrue(any("failure_domain" in x for x in renderer.blockers(data)))
        data=synthetic()
        data["hosts"][0]["address"]="192.0.2.11"
        self.assertTrue(renderer.blockers(data))

    def test_compose_profile_does_not_enable_ha_or_watchdog(self):
        yml=(LAB/"compose.node.yaml").read_text()
        self.assertEqual(yml.count("profiles: [approved-certification]"),2)
        self.assertIn("read_only: true",yml)
        self.assertIn('restart: "no"',yml)
        self.assertNotIn("privileged: true",yml)
        self.assertNotIn("ports:",yml)
        self.assertNotIn("/dev/watchdog:/dev/watchdog",yml)

    def test_physical_ha_contract_on_template_fails_closed(self):
        payload=json.loads((LAB/"ha-acceptance.template.json").read_text())
        self.assertEqual(len(payload["scenarios"]),9)
        self.assertEqual({x["result"] for x in payload["scenarios"]},{"NOT_EXECUTED"})
        decision=contract.assess(payload)
        self.assertEqual(decision["status"],"BLOCKED")
        self.assertFalse(decision["release_eligible"])

    def test_local_host_facts_are_never_attested(self):
        outcome=facts.assess('ID=ubuntu\nVERSION_ID="24.04"','MemTotal: 33554432 kB',8,200*1024**3)
        self.assertEqual(outcome["status"],"UNATTESTED_HOST_FACTS_REVIEW_REQUIRED")
        self.assertFalse(outcome["physical_failure_domain_verified"])
        self.assertFalse(outcome["release_eligible"])
