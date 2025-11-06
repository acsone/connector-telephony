# Copyright 2024 Hunki Enterprises BV
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl-3.0)

import logging

from odoo import fields, models
from odoo.tools import groupby

_logger = logging.getLogger(__name__)


class SmsSms(models.Model):
    _inherit = "sms.sms"

    sms_gateway_id = fields.Many2one("ir.sms.gateway", string="SMS gateway used")

    def _split_by_api(self):
        """Override to split by SMS gateway instead of just API."""
        # First, assign gateways to SMS records that don't have one
        self._assign_gateways()

        # Group by gateway
        for gateway_id, gateway_sms in groupby(
            self, key=lambda sms: sms.sms_gateway_id
        ):
            gateway_sms_list = list(gateway_sms)

            if gateway_id and gateway_id.gateway_type != "iap":
                # For custom gateways, use Custom as API - they'll be handled in _send
                yield "Custom", self.env["sms.sms"].concat(*gateway_sms_list)
            else:
                # For IAP, use standard behavior
                company = self._get_sms_company()
                yield (
                    company._get_sms_api_class()(self.env),
                    self.env["sms.sms"].concat(*gateway_sms_list),
                )

    def _assign_gateways(self):
        """Assign appropriate gateways to SMS records that don't have one."""
        sms_without_gateway = self.filtered(lambda s: not s.sms_gateway_id)
        _logger.info("Found %s SMS records without gateway", len(sms_without_gateway))

        if not sms_without_gateway:
            return

        # Get available gateways
        IrSmsGateway = self.env["ir.sms.gateway"]
        providers = IrSmsGateway._send_get_providers([])
        _logger.info("Available providers: %s", providers.mapped("name"))

        for sms in sms_without_gateway:
            # Find the best gateway for this SMS
            matching_providers = []
            for provider in providers:
                if provider._can_send({"number": sms.number}):
                    matching_providers.append(provider)
                    _logger.info(
                        "Provider %s can send to %s", provider.name, sms.number
                    )

            if matching_providers:
                # Sort by sequence (lower sequence = higher priority)
                best_gateway = min(matching_providers, key=lambda p: p.sequence)
                sms.sms_gateway_id = best_gateway
                _logger.info("Assigned gateway %s to SMS %s", best_gateway.name, sms.id)
            else:
                # If no specific gateway matches, use gateways
                # with no prefix restrictions as fallback
                fallback_providers = providers.filtered(lambda p: not p.prefix)
                if fallback_providers:
                    # Use the fallback gateway with lowest sequence
                    fallback_gateway = min(fallback_providers, key=lambda p: p.sequence)
                    sms.sms_gateway_id = fallback_gateway
                else:
                    # If no fallback either, use the first
                    # available gateway as last resort
                    if providers:
                        last_resort_gateway = min(providers, key=lambda p: p.sequence)
                        sms.sms_gateway_id = last_resort_gateway
                    else:
                        _logger.error("No gateways available for SMS %s", sms.id)

    def _send_with_api(
        self, sms_api, unlink_failed=False, unlink_sent=True, raise_exception=False
    ):
        """Override to handle custom SMS gateways."""
        _logger.info("_send_with_api called with api: %s, SMS: %s", sms_api, self.ids)

        # If no API provided (custom gateway), use custom gateway handling
        if sms_api == "Custom":
            return self._send_with_custom_gateway(
                unlink_failed, unlink_sent, raise_exception
            )

        # Otherwise, use standard IAP handling
        return super()._send_with_api(
            sms_api,
            unlink_failed=unlink_failed,
            unlink_sent=unlink_sent,
            raise_exception=raise_exception,
        )

    def _send_with_custom_gateway(
        self, unlink_failed=False, unlink_sent=True, raise_exception=False
    ):
        """Handle sending with custom SMS gateway."""
        _logger.info("_send_with_custom_gateway called for SMS: %s", self.ids)
        IrSmsGateway = self.env["ir.sms.gateway"]

        # Group SMS by gateway
        gateway_groups = {}
        for sms in self:
            gateway_id = sms.sms_gateway_id.id
            gateway_groups.setdefault(gateway_id, []).append(sms.id)

        all_results = []

        for gateway_id, sms_ids in gateway_groups.items():
            if not gateway_id:
                continue

            gateway = IrSmsGateway.browse(gateway_id)
            sms_records = self.browse(sms_ids)
            _logger.info(
                "Processing %s SMS with gateway %s", len(sms_records), gateway.name
            )

            if gateway.gateway_type == "iap":
                # Use standard IAP for IAP-type gateways
                company = sms_records._get_sms_company()
                sms_api = company._get_sms_api_class()(self.env)
                sms_records._send_with_api(
                    sms_api,
                    unlink_failed=unlink_failed,
                    unlink_sent=unlink_sent,
                    raise_exception=raise_exception,
                )
            else:
                # Use custom gateway
                results = gateway._send_sms_batch(sms_records)
                all_results.extend(results)

        return all_results
