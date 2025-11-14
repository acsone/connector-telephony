# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

from odoo.tests.common import TransactionCase


class TestSmsGatewayMinimal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.gateway = cls.env["ir.sms.gateway"].create(
            {
                "name": "Test Gateway",
                "gateway_type": "iap",
                "sequence": 1,
                "active": True,
            }
        )

    def test_handle_results_success(self):
        """Test _handle_results updates SMS state on success"""
        sms = self.env["sms.sms"].create(
            {
                "number": "+123456789",
                "body": "Test message",
                "sms_gateway_id": self.gateway.id,
            }
        )

        results = [{"uuid": sms.uuid, "state": "success"}]

        self.gateway._handle_results([{"uuid": sms.uuid}], results)
        self.assertEqual(sms.state, "sent")
        self.assertFalse(sms.failure_type)

    def test_handle_results_error(self):
        """Test _handle_results updates SMS state on error"""
        sms = self.env["sms.sms"].create(
            {
                "number": "+987654321",
                "body": "Error message",
                "sms_gateway_id": self.gateway.id,
            }
        )

        results = [{"uuid": sms.uuid, "state": "server_error"}]

        self.gateway._handle_results([{"uuid": sms.uuid}], results)
        self.assertEqual(sms.state, "error")
        self.assertEqual(sms.failure_type, "sms_server")
