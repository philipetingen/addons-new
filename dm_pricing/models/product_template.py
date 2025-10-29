# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ProductTemplate(models.Model):
    """Add customer pricing relationships to product"""
    _inherit = 'product.template'
    
    # Customer pricing (quick-entry records)
    dm_customer_pricelist_ids = fields.One2many(
        'dm.customer.pricelist',
        'product_tmpl_id',
        string='Customer Prices'
    )
    
    dm_customer_pricelist_count = fields.Integer(
        compute='_compute_dm_customer_pricelist_count',
        string='# Customer Prices'
    )
    
    # Add preferred vendor count for smart button
    dm_preferred_vendor_count = fields.Integer(
        compute='_compute_dm_preferred_vendor_count',
        string='# Preferred Vendors'
    )
    
    @api.depends('dm_customer_pricelist_ids')
    def _compute_dm_customer_pricelist_count(self):
        for product in self:
            product.dm_customer_pricelist_count = len(
                product.dm_customer_pricelist_ids.filtered(lambda p: p.active)
            )
    
    @api.depends('seller_ids.dm_preferred_vendor')
    def _compute_dm_preferred_vendor_count(self):
        for product in self:
            product.dm_preferred_vendor_count = len(
                product.seller_ids.filtered(lambda s: s.dm_preferred_vendor)
            )
    
    def action_view_customer_prices(self):
        """Open customer prices for this product"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Customer Prices',
            'res_model': 'dm.customer.pricelist',
            'view_mode': 'tree,form',
            'domain': [('product_tmpl_id', '=', self.id)],
            'context': {
                'default_product_id': self.product_variant_id.id,
                'default_product_tmpl_id': self.id,
            }
        }