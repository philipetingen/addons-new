from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    """
    SPRINT 1: Add auto-confirmation hook when SO is confirmed.
    When both SO and PO are confirmed, deal should auto-confirm.
    """
    _inherit = 'sale.order'
    
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='DM Deal',
        readonly=True,
        index=True,
        help='Reference to originating DonnaMello deal'
    )
    
    def action_confirm(self):
        """
        Override to trigger deal auto-confirmation.
        SPRINT 1 CRITICAL: This checks if both SO and PO are confirmed,
        then auto-confirms the deal.
        """
        res = super(SaleOrder, self).action_confirm()
        
        # Check each confirmed SO for deal auto-confirmation
        for order in self:
            if order.dm_deal_id and order.dm_deal_id.state == 'validated':
                try:
                    # Trigger auto-confirmation check
                    order.dm_deal_id._check_auto_confirmation()
                    
                    _logger.info(
                        f"SO {order.name} confirmed - triggered auto-confirmation check for deal {order.dm_deal_id.name}"
                    )
                except Exception as e:
                    _logger.error(
                        f"Error in deal auto-confirmation from SO {order.name}: {str(e)}"
                    )
                    # Don't block SO confirmation even if deal confirmation fails
        
        return res


class SaleOrderLine(models.Model):
    """Link to deal line for traceability"""
    _inherit = 'sale.order.line'
    
    dm_deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        readonly=True,
        index=True,
        help='Reference to originating deal line'
    )