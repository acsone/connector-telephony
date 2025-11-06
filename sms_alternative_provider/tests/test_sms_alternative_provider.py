# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

from unittest.mock import patch

from odoo.tests.common import TransactionCase


class TestSmsAlternativeProvider(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.iap_gateway = cls.env.ref("sms_alternative_provider.gateway_iap")
        # Ensure the IAP gateway is active and has no prefix restrictions
        cls.iap_gateway.write(
            {
                "active": True,
                "prefix": False,
                "sequence": 10,
            }
        )

    def test_iap(self):
        """Test that without extra configuration, we just use IAP"""
        self.env["iap.account"].search([("service_name", "=", "sms")]).unlink()
        sms = self.env["sms.sms"].create(
            {
                "number": "424242",
                "body": "hello world",
            }
        )

        # Verify the SMS was created without a gateway initially
        self.assertFalse(sms.sms_gateway_id, "SMS should not have gateway initially")

        # Mock the IAP call
        with patch.object(type(self.env["sms.sms"]), "_send_with_api") as mock_send:
            # Simulate successful send
            def side_effect(
                sms_api, unlink_failed=False, unlink_sent=True, raise_exception=False
            ):
                # The gateway should be assigned by now
                sms.write({"state": "sent"})
                return [{"uuid": sms.uuid, "state": "success"}]

            mock_send.side_effect = side_effect
            sms.send(unlink_sent=False)

            # Check that the mock was called
            self.assertTrue(mock_send.called, "_send_with_api should have been called")

            # Clear cache and re-read the record to get updated values
            self.env.invalidate_all()
            sms = self.env["sms.sms"].browse(sms.id)

            self.assertEqual(sms.state, "sent")
            expected_msg = (
                f"SMS should use IAP gateway. Got {sms.sms_gateway_id}, "
                f"expected {self.iap_gateway}"
            )
            self.assertEqual(sms.sms_gateway_id, self.iap_gateway, expected_msg)

    def test_restrictions(self):
        """Test that we can restrict gateways to certain numbers"""
        # Create gateways with different prefixes
        # Give the "No Restriction Gateway" a LOWER sequence
        gw_no_restriction = self.env["ir.sms.gateway"].create(
            {
                "name": "No Restriction Gateway",
                "gateway_type": "iap",
                "prefix": False,
                # LOWER sequence so it's preferred over original IAP gateway
                "sequence": 5,
                "active": True,
            }
        )
        # Remove unused gw_31 variable since it's not used in the test
        # gw_31 = self.env["ir.sms.gateway"].create({
        #     "name": "+31 Gateway",
        #     "gateway_type": "iap",
        #     "prefix": "+31",
        #     "sequence": 1,
        #     "active": True,
        # })
        gw_32_49 = self.env["ir.sms.gateway"].create(
            {
                "name": "+32+49 Gateway",
                "gateway_type": "iap",
                "prefix": "+32 +49",
                "sequence": 2,
                "active": True,
            }
        )

        # Test German number (+49) should use gw_32_49
        sms = self.env["sms.sms"].create(
            {
                "number": "+49 424242",
                "body": "hello world",
            }
        )

        with patch.object(type(self.env["sms.sms"]), "_send_with_api") as mock_send:

            def side_effect(
                sms_api, unlink_failed=False, unlink_sent=True, raise_exception=False
            ):
                sms.write({"state": "sent"})
                return [{"uuid": sms.uuid, "state": "success"}]

            mock_send.side_effect = side_effect
            sms.send(unlink_sent=False)

            # Clear cache and re-read the record
            self.env.invalidate_all()
            sms = self.env["sms.sms"].browse(sms.id)

            self.assertEqual(sms.state, "sent")
            expected_msg = (
                f"German number should use +32+49 gateway. Got {sms.sms_gateway_id}, "
                f"expected {gw_32_49}"
            )
            self.assertEqual(sms.sms_gateway_id, gw_32_49, expected_msg)

        # Test US number (+1) should use gw_no_restriction
        sms = self.env["sms.sms"].create(
            {
                "number": "+1 424242",
                "body": "hello world",
            }
        )

        with patch.object(type(self.env["sms.sms"]), "_send_with_api") as mock_send:

            def side_effect(
                sms_api, unlink_failed=False, unlink_sent=True, raise_exception=False
            ):
                sms.write({"state": "sent"})
                return [{"uuid": sms.uuid, "state": "success"}]

            mock_send.side_effect = side_effect
            sms.send(unlink_sent=False)

            # Clear cache and re-read the record
            self.env.invalidate_all()
            sms = self.env["sms.sms"].browse(sms.id)

            self.assertEqual(sms.state, "sent")
            expected_msg = (
                f"US number should use no-restriction gateway. Got "
                f"{sms.sms_gateway_id}, expected {gw_no_restriction}"
            )
            self.assertEqual(sms.sms_gateway_id, gw_no_restriction, expected_msg)

        # Test no provider found scenario
        # Set ALL gateways to have prefix restrictions that don't match +1
        gw_no_restriction.prefix = "+2"
        self.iap_gateway.prefix = "+3"  # Also restrict the original IAP gateway

        sms = self.env["sms.sms"].create(
            {
                "number": "+1 424242",
                "body": "hello world",
            }
        )

        # This should log an error and set SMS to error state
        sms.send()

        # Clear cache and re-read the record
        self.env.invalidate_all()
        sms = self.env["sms.sms"].browse(sms.id)
        self.assertEqual(sms.state, "error")
