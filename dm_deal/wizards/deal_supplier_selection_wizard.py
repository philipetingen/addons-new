# -*- coding: utf-8 -*-
"""
Supplier Selection Wizard for Deal Lines
Shows available vendors when product has multiple supplier options
"""

from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DealSupplierSelectionWizard(models.TransientModel):
    """
    Wizard to select supplier when multiple vendors available for a product
    """
    _name = 'dm.deal.supplier.selection.wizard'
    _description = 'Select Supplier for Deal'
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        readonly=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        readonly=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Packaging',
        required=True,
        readonly=True
    )
    
    quantity_packaging = fields.Float(
        string='Quantity (Packages)',
        required=True,
        readonly=True,
        digits=(16, 3)
    )
    
    available_supplier_ids = fields.One2many(
        'dm.deal.supplier.selection.line',
        'wizard_id',
        string='Available Suppliers'
    )
    
    # Store available supplier partner IDs for domain
    available_supplier_partner_ids = fields.Many2many(
        'res.partner',
        string='Available Supplier Partners',
        compute='_compute_available_supplier_partner_ids',
        store=False
    )
    
    selected_supplier_id = fields.Many2one(
        'res.partner',
        string='Selected Supplier',
        required=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        string='Deal Currency',
        readonly=True
    )
    
    @api.depends('available_supplier_ids', 'available_supplier_ids.partner_id')
    def _compute_available_supplier_partner_ids(self):
        """Compute list of available supplier partners for domain"""
        for wizard in self:
            if wizard.available_supplier_ids:
                wizard.available_supplier_partner_ids = wizard.available_supplier_ids.mapped('partner_id')
            else:
                wizard.available_supplier_partner_ids = False
    
    @api.model
    def default_get(self, fields_list):
        """Populate wizard with available suppliers"""
        res = super().default_get(fields_list)
        
        # Get context values
        deal_id = self.env.context.get('deal_id')
        product_id = self.env.context.get('product_id')
        packaging_id = self.env.context.get('product_packaging_id')
        quantity = self.env.context.get('quantity_packaging', 1.0)
        
        if deal_id and product_id and packaging_id:
            res['deal_id'] = deal_id
            res['product_id'] = product_id
            res['product_packaging_id'] = packaging_id
            res['quantity_packaging'] = quantity
            
            # Get available vendor pricelists
            deal = self.env['dm.deal'].browse(deal_id)
            vendor_pricelists = self.env['dm.vendor.pricelist'].search([
                ('product_id', '=', product_id),
                ('product_packaging_id', '=', packaging_id),
                ('min_qty_packages', '<=', quantity),
                ('active', '=', True),
                '|',
                ('date_start', '<=', fields.Date.context_today(self)),
                ('date_start', '=', False),
                '|',
                ('date_end', '>=', fields.Date.context_today(self)),
                ('date_end', '=', False),
            ])
            
            # Filter by deal currency if set
            if deal.currency_id:
                vendor_pricelists = vendor_pricelists.filtered(
                    lambda pl: pl.currency_id == deal.currency_id
                )
            
            # Create wizard lines
            supplier_lines = []
            for pricelist in vendor_pricelists:
                supplier_lines.append((0, 0, {
                    'partner_id': pricelist.partner_id.id,
                    'package_price': pricelist.package_price,
                    'currency_id': pricelist.currency_id.id,
                    'lead_time_days': pricelist.lead_time_days,
                    'preferred_vendor': pricelist.preferred_vendor,
                    'min_qty_packages': pricelist.min_qty_packages,
                    'vendor_moq_packages': pricelist.vendor_moq_packages,
                }))
            
            res['available_supplier_ids'] = supplier_lines
            
            # Auto-select preferred vendor if exists
            preferred = vendor_pricelists.filtered(lambda pl: pl.preferred_vendor)
            if preferred:
                res['selected_supplier_id'] = preferred[0].partner_id.id
        
        return res
    
    def action_confirm_supplier(self):
        """Apply selected supplier to deal and create line"""
        self.ensure_one()
        
        if not self.selected_supplier_id:
            raise UserError("Please select a supplier")
        
        # Force update deal supplier
        self.deal_id.sudo().write({'supplier_id': self.selected_supplier_id.id})
        
        _logger.info(
            f"Deal {self.deal_id.name}: Supplier set to {self.selected_supplier_id.name} via wizard"
        )
        
        # Check consistency if supplier already set differently
        if self.deal_id.supplier_id and self.deal_id.supplier_id != self.selected_supplier_id:
            raise UserError(
                f"Deal is already allocated to supplier '{self.deal_id.supplier_id.name}'. "
                f"Cannot mix suppliers in one deal."
            )
        
        # Return action to close wizard and refresh deal form
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal',
            'res_id': self.deal_id.id,
            'view_mode': 'form',
            'target': 'current',
            'context': {
                'supplier_selected': True,
                'selected_supplier_id': self.selected_supplier_id.id,
                'product_id': self.product_id.id,
                'product_packaging_id': self.product_packaging_id.id,
                'quantity_packaging': self.quantity_packaging,
            },
            'flags': {'mode': 'edit'}  # Force form to edit mode
        }


class DealSupplierSelectionLine(models.TransientModel):
    """
    Line item showing supplier option with pricing details
    """
    _name = 'dm.deal.supplier.selection.line'
    _description = 'Supplier Selection Option'
    _order = 'preferred_vendor desc, package_price asc'
    
    wizard_id = fields.Many2one(
        'dm.deal.supplier.selection.wizard',
        required=True,
        ondelete='cascade'
    )
    
    partner_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        required=True,
        readonly=True
    )
    
    package_price = fields.Float(
        string='Price/Package',
        digits=(16, 6),
        readonly=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        readonly=True
    )
    
    lead_time_days = fields.Integer(
        string='Lead Time (days)',
        readonly=True
    )
    
    preferred_vendor = fields.Boolean(
        string='Preferred',
        readonly=True
    )
    
    min_qty_packages = fields.Float(
        string='Min Qty Break',
        digits=(16, 3),
        readonly=True,
        help='Minimum quantity for this price tier'
    )
    
    vendor_moq_packages = fields.Float(
        string='Vendor MOQ',
        digits=(16, 3),
        readonly=True,
        help='Vendor minimum order quantity'
    )
    
    def action_select_this_supplier(self):
        """Quick action to select this supplier"""
        self.ensure_one()
        self.wizard_id.selected_supplier_id = self.partner_id
        return self.wizard_id.action_confirm_supplier()