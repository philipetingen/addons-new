from odoo import models, fields, api


class AccountMove(models.Model):
    """Extend account.move with DM deal tracking"""
    _inherit = 'account.move'
    
    # Deal tracking
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='DM Deal',
        index=True,
        tracking=True
    )
    
    dm_production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        index=True
    )
    
    dm_shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        index=True
    )
    
    # Invoice split tracking
    is_product_invoice = fields.Boolean(
        string='Is Product Invoice',
        help='This is the product portion of a split invoice'
    )
    
    is_service_invoice = fields.Boolean(
        string='Is Service Invoice',
        help='This is the service portion of a split invoice'
    )
    
    split_config_id = fields.Many2one(
        'dm.invoice.split.config',
        string='Split Configuration'
    )
    
    # Downpayment tracking
    downpayment_ids = fields.Many2many(
        'dm.downpayment.request',
        'dm_dp_invoice_rel',
        'invoice_id',
        'dp_id',
        string='Applied Downpayments'
    )
    
    downpayment_amount = fields.Monetary(
        string='Applied Downpayment',
        currency_field='currency_id',
        compute='_compute_downpayment_amount',
        store=True
    )
    
    @api.depends('downpayment_ids', 'downpayment_ids.amount_received')
    def _compute_downpayment_amount(self):
        """Compute total applied downpayment"""
        for invoice in self:
            invoice.downpayment_amount = sum(
                invoice.downpayment_ids.mapped('amount_received')
            )
    
    def _compute_amount(self):
        """Override to consider downpayments"""
        res = super()._compute_amount()
        
        for invoice in self:
            if invoice.downpayment_amount:
                # Adjust amount due considering downpayments
                invoice.amount_residual -= invoice.downpayment_amount
        
        return res