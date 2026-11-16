"""No virtual lab or machine assertion can impersonate a witnessed HA/legal signoff."""
import json
from pathlib import Path
from unittest import TestCase

D=Path(__file__).resolve().parents[1]/"docs/verification/sec001-r03"
class IndependentAcceptanceTests(TestCase):
    def test_three_real_hosts_not_fabricated(self):
        d=json.loads((D/"REAL_HOST_DISCOVERY_REQUEST.template.json").read_text())
        assert len(d["hosts"])==3
        assert all(h["actual_asset_id"] is None and h["actual_private_ip"] is None for h in d["hosts"])
        assert d["actual_hosts_identified"] is False and d["release_eligible"] is False
        assert d["fencing"]["explicit_host_fault_authorization"] is False

    def test_physical_faults_are_not_marked_executed(self):
        d=json.loads((D/"PHYSICAL_HA_WITNESS.template.json").read_text())
        assert len(d["scenarios"])==9
        assert all(x["result"]=="NOT_EXECUTED" and x["artifact_sha256"] is None for x in d["scenarios"])
        assert d["independent_signed_ha_approval"] is False and d["release_eligible"] is False

    def test_all_eight_final_oci_signoffs_are_unsigned(self):
        d=json.loads((D/"FINAL_OCI_LEGAL_SIGNOFF_REQUEST.template.json").read_text())
        assert len(d["image_reviews"])==8
        assert all(x["legal_decision"]=="PENDING_ACCOUNTABLE_REVIEW" and
                   x["oci_manifest_sha256"] is None and
                   x["signed_document_sha256"] is None for x in d["image_reviews"])
        assert d["license_notice_approval"] is False and d["release_eligible"] is False
