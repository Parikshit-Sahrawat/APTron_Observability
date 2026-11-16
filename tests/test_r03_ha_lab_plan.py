"""No host may be contacted solely because someone authored a HA lab inventory."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "ci"))
import r03_ha_lab_plan as lab  # noqa: E402
import r03_ha_evidence_contract as ha  # noqa: E402

D="sha256:"+("c"*64)

def inventory():
    return {
        "environment":"ISOLATED_EXISTING_HOSTS",
        "owner_authorized":True,
        "synthetic_data_only":True,
        "production_network_connected":False,
        "images":{"postgres":D,"patroni":D,"etcd":D},
        "hosts":[
            {"host_id":f"host-{i}","failure_domain":f"physical-domain-{i}",
             "physical_host":True,"owner_authorized":True,"host_attestation_sha256":D}
            for i in range(3)
        ],
    }

class LabPlanTests(unittest.TestCase):
    def test_default_is_blocked_and_no_remote_actions_exist(self):
        result=lab.prepare({})
        self.assertEqual(result["status"],"BLOCKED")
        self.assertFalse(result["contains_host_commands"])
        self.assertFalse(result["release_eligible"])

    def test_authorized_manifest_only_prepares_never_certifies(self):
        result=lab.prepare(inventory())
        self.assertEqual(result["status"],"PREPARED_NOT_EXECUTED")
        self.assertEqual(len(result["scenario_plan"]),len(ha.REQUIRED))
        self.assertTrue(all(x["status"]=="NOT_EXECUTED" for x in result["scenario_plan"]))
        self.assertEqual(result["independent_dba_certification"],"NOT_RECEIVED")
        self.assertFalse(result["physical_fencing_executed"])

    def test_shared_failure_domain_is_blocked(self):
        data=inventory()
        data["hosts"][2]["failure_domain"]=data["hosts"][0]["failure_domain"]
        self.assertEqual(lab.prepare(data)["status"],"BLOCKED")

    def test_missing_host_authorization_is_blocked(self):
        data=inventory()
        data["hosts"][1]["owner_authorized"]=False
        self.assertEqual(lab.prepare(data)["status"],"BLOCKED")

    def test_production_network_or_unidentified_images_fail_closed(self):
        for field,value in [("production_network_connected",True),
                            ("synthetic_data_only",False)]:
            data=inventory()
            data[field]=value
            self.assertEqual(lab.prepare(data)["status"],"BLOCKED")
        data=inventory()
        data["images"]["patroni"]="patroni:latest"
        self.assertEqual(lab.prepare(data)["status"],"BLOCKED")

if __name__=="__main__":
    unittest.main()
