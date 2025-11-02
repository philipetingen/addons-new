from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    """
    Phase 4B: Simplified - removed auto-confirmation hook.
    
    In Phase 4B workflow:
    - Deal confirmation creates SO/PO and auto-confirms them
    - SO/PO confirmation does NOT trigger deal state changes
    - This is a cleaner separation of concerns
    """
    _inherit = 'purchase.order'
    
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='DM Deal',
        readonly=True,
        index=True,
        help='Reference to originating DonnaMello deal'
    )


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