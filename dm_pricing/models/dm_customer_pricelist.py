# -*- coding: utf-8 -*-
"""
Quick-entry interface for customer pricing.
Creates/updates standard product.pricelist.item records.
Maintains bilateral sync.
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmCustomerPricelist(models.Model):
    """
    Quick-entry interface for customer-specific pricing.
    
    ARCHITECTURE:
    - This is a convenience model for managing prices per customer
    - It creates/updates standard product.pricelist.item records
    - Bilateral sync ensures consistency
    - One pricelist per customer (auto-created if needed)
    """
    _name = 'dm.customer.pricelist'
    _description = 'Customer Specific Pricing (Quick Entry)'
    _rec_name = 'display_name'
    _order = 'partner_id, product_id, product_packaging_id'
    
    # Core relationships
    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        domain=[('is_company', '=', True)],
        ondelete='cascade',
        index=True
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    product_tmpl_id = fields.Many2one(
        'product.template',
        related='product_id.product_tmpl_id',
        store=True,
        string='Product Template'
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Package Type',
        required=True,
        domain="[('product_id', '=', product_id)]"
    )
    
    # Customer codes
    customer_product_code = fields.Char(
        string='Customer Product Code',
        index=True
    )
    
    customer_product_description = fields.Text(
        string='Customer Description'
    )
    
    # Pricing (6-decimal)
    package_price = fields.Float(
        string='Price per Package',
        digits=(16, 6),
        required=True
    )
    
    # Computed references
    unit_price = fields.Float(
        string='Price per Unit',
        compute='_compute_unit_price',
        store=True,
        digits=(16, 6)
    )
    
    price_per_kg = fields.Float(
        string='Price per kg',
        compute='_compute_price_per_kg',
        store=True,
        digits=(16, 3)
    )
    
    # MOQ
    moq_packages = fields.Float(
        string='MOQ (Packages)',
        digits=(16, 3),
        default=1.0
    )
    
    moq_enforcement = fields.Selection([
        ('none', 'No Enforcement'),
        ('warning', 'Warning Only'),
        ('strict', 'Block Order'),
        ('approval', 'Requires Approval')
    ], default='warning')
    
    # Validity
    date_start = fields.Date(
        string='Valid From',
        default=fields.Date.context_today
    )
    
    date_end = fields.Date(
        string='Valid Until'
    )
    
    # Currency
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id
    )
    
    # Additional terms
    lead_time = fields.Integer(string='Lead Time (days)')
    payment_term_id = fields.Many2one('account.payment.term')
    incoterm_id = fields.Many2one('account.incoterms')
    
    # Status
    active = fields.Boolean(default=True)
    display_name = fields.Char(compute='_compute_display_name', store=True)
    notes = fields.Text()
    
    # BILATERAL SYNC: Link to actual pricelist item
    pricelist_item_id = fields.Many2one(
        'product.pricelist.item',
        string='Pricelist Item',
        readonly=True,
        help='Linked standard pricelist item'
    )
    
    pricelist_id = fields.Many2one(
        'product.pricelist',
        string='Customer Pricelist',
        compute='_compute_pricelist_id',
        store=True,
        help='Customer-specific pricelist'
    )
    
    # ==========================================
    # COMPUTED METHODS
    # ==========================================
    
    @api.depends('partner_id')
    def _compute_pricelist_id(self):
        """Get or create customer-specific pricelist"""
        for rec in self:
            if rec.partner_id:
                rec.pricelist_id = rec._get_or_create_customer_pricelist()
            else:
                rec.pricelist_id = False
    
    @api.depends('partner_id', 'product_id', 'product_packaging_id')
    def _compute_display_name(self):
        for rec in self:
            parts = []
            if rec.partner_id:
                parts.append(rec.partner_id.name)
            if rec.product_id:
                parts.append(rec.product_id.name)
            if rec.product_packaging_id:
                parts.append(f"({rec.product_packaging_id.name})")
            rec.display_name = ' - '.join(parts) if parts else 'New'
    
    @api.depends('package_price', 'product_packaging_id.qty')
    def _compute_unit_price(self):
        for rec in self:
            if rec.product_packaging_id and rec.product_packaging_id.qty:
                rec.unit_price = rec.package_price / rec.product_packaging_id.qty
            else:
                rec.unit_price = rec.package_price
    
    @api.depends('package_price', 'product_packaging_id')
    def _compute_price_per_kg(self):
        for rec in self:
            if not rec.product_packaging_id:
                rec.price_per_kg = 0
                continue
            
            # Use packaging net weight if available
            if hasattr(rec.product_packaging_id, 'packaging_net_weight'):
                total_weight = rec.product_packaging_id.packaging_net_weight or 0
            else:
                total_weight = (rec.product_packaging_id.qty or 0) * (rec.product_id.weight or 0)
            
            if total_weight > 0:
                rec.price_per_kg = rec.package_price / total_weight
            else:
                rec.price_per_kg = 0
    
    # ==========================================
    # BILATERAL SYNC LOGIC
    # ==========================================
    
    def _get_or_create_customer_pricelist(self):
        """Get or create pricelist for customer in correct currency"""
        self.ensure_one()
        
        Pricelist = self.env['product.pricelist']
        
        # Search for pricelist with matching name pattern (our convention)
        pricelist_name = f"{self.partner_id.name} Pricelist ({self.currency_id.name})"
        
        pricelist = Pricelist.search([
            ('name', '=', pricelist_name),
            ('currency_id', '=', self.currency_id.id),
            ('company_id', 'in', [self.env.company.id, False])
        ], limit=1)
        
        if not pricelist:
            # Create new pricelist for this customer-currency combination
            pricelist = Pricelist.create({
                'name': pricelist_name,
                'currency_id': self.currency_id.id,
                'company_id': self.env.company.id,
                'active': True,
            })
            
            # Set as customer's default pricelist if they don't have one in this currency
            if self.partner_id.property_product_pricelist.currency_id != self.currency_id:
                # Only set if customer's current pricelist is different currency
                self.partner_id.property_product_pricelist = pricelist
            
            _logger.info(f"Created pricelist {pricelist.name} for {self.partner_id.name}")
        
        return pricelist
    
    def _sync_to_pricelist_item(self):
        """Create or update linked pricelist item"""
        self.ensure_one()
        
        PricelistItem = self.env['product.pricelist.item']
        
        # Prepare values
        item_vals = {
            'pricelist_id': self.pricelist_id.id,
            'product_tmpl_id': self.product_tmpl_id.id,
            'product_id': self.product_id.id,
            'date_start': self.date_start,
            'date_end': self.date_end,
            'compute_price': 'fixed',  # Use our DM pricing
            
            # DM package pricing fields
            'dm_is_package_price': True,
            'dm_packaging_id': self.product_packaging_id.id,
            'dm_package_price': self.package_price,
            'dm_moq_packages': self.moq_packages,
            'dm_moq_enforcement': self.moq_enforcement,
            'dm_customer_product_code': self.customer_product_code,
            'dm_customer_description': self.customer_product_description,
            
            # Link back
            'dm_customer_pricelist_id': self.id,
        }
        
        if self.pricelist_item_id:
            # Update existing
            self.pricelist_item_id.write(item_vals)
            _logger.debug(f"Updated pricelist item {self.pricelist_item_id.id}")
        else:
            # Create new
            item = PricelistItem.create(item_vals)
            self.pricelist_item_id = item
            _logger.debug(f"Created pricelist item {item.id}")
    
    # ==========================================
    # CRUD OVERRIDES FOR SYNC
    # ==========================================
    
    @api.model
    def create(self, vals):
        """Create and sync to pricelist"""
        rec = super().create(vals)
        rec._sync_to_pricelist_item()
        return rec
    
    def write(self, vals):
        """Update and sync to pricelist"""
        res = super().write(vals)
        
        # Sync if relevant fields changed
        sync_fields = {
            'package_price', 'product_packaging_id', 'moq_packages',
            'moq_enforcement', 'date_start', 'date_end',
            'customer_product_code', 'customer_product_description'
        }
        
        if any(field in vals for field in sync_fields):
            for rec in self:
                rec._sync_to_pricelist_item()
        
        return res
    
    def unlink(self):
        """Delete linked pricelist items"""
        items_to_delete = self.mapped('pricelist_item_id')
        res = super().unlink()
        items_to_delete.unlink()
        return res
    
    # ==========================================
    # UTILITY METHODS
    # ==========================================
    
    @api.model
    def get_customer_price(self, partner_id, product_id, packaging_id, date=None, currency_id=None):
        """Get customer price - maintains API compatibility"""
        domain = [
            ('partner_id', '=', partner_id),
            ('product_id', '=', product_id),
            ('product_packaging_id', '=', packaging_id),
            ('active', '=', True)
        ]
        
        if currency_id:
            domain.append(('currency_id', '=', currency_id))
        
        if not date:
            date = fields.Date.context_today(self)
        
        items = self.search(domain)
        valid_items = items.filtered(lambda i: i.is_valid(date))
        
        return valid_items[0].package_price if valid_items else False
    
    def is_valid(self, date=None):
        """Check validity"""
        self.ensure_one()
        if not date:
            date = fields.Date.context_today(self)
        
        if self.date_start and date < self.date_start:
            return False
        if self.date_end and date > self.date_end:
            return False
        
        return self.active
    
    # ==========================================
    # CONSTRAINTS
    # ==========================================
    
    _sql_constraints = [
        ('unique_customer_product_package',
         'UNIQUE(partner_id, product_id, product_packaging_id, currency_id)',
         'Only one price per customer-product-package-currency combination!'),
        ('positive_price', 
         'CHECK(package_price > 0)', 
         'Package price must be positive!'),
    ]