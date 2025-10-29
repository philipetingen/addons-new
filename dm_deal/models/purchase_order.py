from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    """
    SPRINT 1: Add auto-confirmation hook when PO is confirmed.
    When both SO and PO are confirmed, deal should auto-confirm.
    """
    _inherit = 'purchase.order'
    
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='DM Deal',
        readonly=True,
        index=True,
        help='Reference to originating DonnaMello deal'
    )
    
    def button_confirm(self):
        """
        Override to trigger deal auto-confirmation.
        SPRINT 1 CRITICAL: This checks if both SO and PO are confirmed,
        then auto-confirms the deal.
        """
        res = super(PurchaseOrder, self).button_confirm()
        
        # Check each confirmed PO for deal auto-confirmation
        for order in self:
            if order.dm_deal_id and order.dm_deal_id.state == 'validated':
                try:
                    # Trigger auto-confirmation check
                    order.dm_deal_id._check_auto_confirmation()
                    
                    _logger.info(
                        f"PO {order.name} confirmed - triggered auto-confirmation check for deal {order.dm_deal_id.name}"
                    )
                except Exception as e:
                    _logger.error(
                        f"Error in deal auto-confirmation from PO {order.name}: {str(e)}"
                    )
                    # Don't block PO confirmation even if deal confirmation fails
        
        return res


class PurchaseOrderLine(models.Model):
    """Link to deal line for traceability"""
    _inherit = 'purchase.order.line'
    
    dm_deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        readonly=True,
        index=True,
        help='Reference to originating deal line'
    )