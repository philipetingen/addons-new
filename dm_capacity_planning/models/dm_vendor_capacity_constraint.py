# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmVendorCapacityConstraint(models.Model):
    """
    Specific Capacity Constraints
    
    Optional product-specific or category-specific capacity limits
    that sit within the total vendor capacity. These represent real
    production line constraints (e.g., Lines 1-2 can only make Products A & B).
    
    Multiple constraints can overlap - the system checks ALL of them.
    Example: Constraint 1 (4 TEU) + Constraint 2 (4 TEU) = 8 TEU total,
    but vendor total might be 10 TEU. System ensures both constraints
    and total are respected.
    """
    _name = 'dm.vendor.capacity.constraint'
    _description = 'Vendor Capacity Constraint'
    _order = 'vendor_capacity_id, sequence, id'
    _rec_name = 'name'
    
    # =========================================================================
    # BASIC INFORMATION
    # =========================================================================
    
    vendor_capacity_id = fields.Many2one(
        'dm.vendor.capacity',
        string='Vendor Capacity',
        required=True,
        ondelete='cascade',
        index=True,
        help='Parent capacity record this constraint belongs to'
    )
    
    vendor_id = fields.Many2one(
        related='vendor_capacity_id.vendor_id',
        string='Vendor',
        store=True,
        readonly=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order'
    )
    
    name = fields.Char(
        string='Constraint Name',
        required=True,
        help='e.g., "Lines 1-2 (Products A, B)" or "Chocolate Production Lines"'
    )
    
    # =========================================================================
    # CONSTRAINT SCOPE
    # =========================================================================
    
    constraint_type = fields.Selection([
        ('product', 'Specific Products'),
        ('category', 'Product Category'),
        # Future: ('product_line', 'Production Line'),
    ], string='Constraint Type',
        required=True,
        default='product',
        help='What this constraint applies to'
    )
    
    # === PRODUCT SELECTION ===
    product_ids = fields.Many2many(
        'product.product',
        'vendor_constraint_product_rel',
        'constraint_id',
        'product_id',
        string='Products',
        domain=[('type', 'in', ['product', 'consu'])],
        help='Specific products this constraint applies to. Leave empty to apply to all products.'
    )
    
    product_count = fields.Integer(
        compute='_compute_product_count',
        string='# Products'
    )
    
    # === CATEGORY SELECTION ===
    category_ids = fields.Many2many(
        'product.category',
        'vendor_constraint_category_rel',
        'constraint_id',
        'category_id',
        string='Categories',
        help='Product categories this constraint applies to'
    )
    
    category_count = fields.Integer(
        compute='_compute_category_count',
        string='# Categories'
    )
    
    # =========================================================================
    # CAPACITY LIMIT
    # =========================================================================
    
    entry_mode = fields.Selection([
        ('teu', 'Enter in TEU'),
        ('containers', 'Enter in Containers')
    ], string='Entry Method',
        default='teu',
        required=True,
        help='How to enter this constraint limit'
    )
    
    # === OPTION 1: Direct TEU Entry ===
    max_capacity_teu = fields.Float(
        string='Max Capacity (TEU/Month)',
        digits=(16, 2),
        help='Maximum TEU per month for products matching this constraint'
    )
    
    # === OPTION 2: Container-Based Entry ===
    container_type_id = fields.Many2one(
        'dm.container.type',
        string='Container Type',
        help='Container type for capacity calculation'
    )
    
    max_capacity_containers = fields.Float(
        string='Max Capacity (Containers/Month)',
        digits=(16, 2),
        help='Maximum containers per month'
    )
    
    # === AUTO-CALCULATED EFFECTIVE LIMIT ===
    effective_max_capacity_teu = fields.Float(
        string='Effective Max (TEU/Month)',
        compute='_compute_effective_max_capacity_teu',
        store=True,
        digits=(16, 2),
        help='Final capacity limit in TEU'
    )
    
    # =========================================================================
    # DESCRIPTION & STATUS
    # =========================================================================
    
    description = fields.Text(
        string='Description',
        help='e.g., "Production lines 1-2 share equipment and can handle chocolate products"'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Inactive constraints are ignored in capacity calculations'
    )
    
    # =========================================================================
    # DISPLAY HELPERS
    # =========================================================================
    
    display_scope = fields.Char(
        compute='_compute_display_scope',
        string='Applies To'
    )
    
    # =========================================================================
    # COMPUTE METHODS
    # =========================================================================
    
    @api.depends('product_ids')
    def _compute_product_count(self):
        """Count selected products"""
        for record in self:
            record.product_count = len(record.product_ids)
    
    @api.depends('category_ids')
    def _compute_category_count(self):
        """Count selected categories"""
        for record in self:
            record.category_count = len(record.category_ids)
    
    @api.depends('entry_mode', 'max_capacity_teu', 'max_capacity_containers',
                 'container_type_id', 'container_type_id.teu_factor')
    def _compute_effective_max_capacity_teu(self):
        """Calculate effective max capacity in TEU"""
        for record in self:
            if record.entry_mode == 'teu':
                record.effective_max_capacity_teu = record.max_capacity_teu or 0.0
            else:  # containers
                if record.max_capacity_containers and record.container_type_id:
                    teu_factor = record.container_type_id.teu_factor or 1.0
                    record.effective_max_capacity_teu = record.max_capacity_containers * teu_factor
                else:
                    record.effective_max_capacity_teu = 0.0
    
    @api.depends('constraint_type', 'product_ids', 'category_ids')
    def _compute_display_scope(self):
        """Generate human-readable scope"""
        for record in self:
            if record.constraint_type == 'product':
                if record.product_ids:
                    names = record.product_ids[:3].mapped('name')
                    if len(record.product_ids) > 3:
                        names.append(f"+ {len(record.product_ids) - 3} more")
                    record.display_scope = ", ".join(names)
                else:
                    record.display_scope = "All products"
            elif record.constraint_type == 'category':
                if record.category_ids:
                    names = record.category_ids[:3].mapped('name')
                    if len(record.category_ids) > 3:
                        names.append(f"+ {len(record.category_ids) - 3} more")
                    record.display_scope = ", ".join(names)
                else:
                    record.display_scope = "All categories"
            else:
                record.display_scope = ""
    
    # =========================================================================
    # CONSTRAINTS & VALIDATION
    # =========================================================================
    
    @api.constrains('entry_mode', 'max_capacity_teu', 'max_capacity_containers', 'container_type_id')
    def _check_capacity_entry(self):
        """Validate capacity entry based on mode"""
        for record in self:
            if record.entry_mode == 'teu':
                if not record.max_capacity_teu or record.max_capacity_teu <= 0:
                    raise ValidationError(
                        _("Please enter a positive max capacity value in TEU.")
                    )
            else:  # containers
                if not record.max_capacity_containers or record.max_capacity_containers <= 0:
                    raise ValidationError(
                        _("Please enter a positive number of containers.")
                    )
                if not record.container_type_id:
                    raise ValidationError(
                        _("Please select a container type for capacity calculation.")
                    )
    
    @api.constrains('constraint_type', 'product_ids', 'category_ids')
    def _check_scope_selection(self):
        """Ensure appropriate selection based on type"""
        for record in self:
            if record.constraint_type == 'product':
                if not record.product_ids:
                    raise ValidationError(
                        _("Please select at least one product for this product-based constraint.")
                    )
            elif record.constraint_type == 'category':
                if not record.category_ids:
                    raise ValidationError(
                        _("Please select at least one category for this category-based constraint.")
                    )
    
    @api.constrains('effective_max_capacity_teu', 'vendor_capacity_id')
    def _check_constraint_vs_total(self):
        """Warn if constraint exceeds total capacity"""
        for record in self:
            if (record.effective_max_capacity_teu and 
                record.vendor_capacity_id.effective_capacity_teu and
                record.effective_max_capacity_teu > record.vendor_capacity_id.effective_capacity_teu):
                
                _logger.warning(
                    f"Constraint '{record.name}' ({record.effective_max_capacity_teu} TEU) "
                    f"exceeds total vendor capacity "
                    f"({record.vendor_capacity_id.effective_capacity_teu} TEU). "
                    f"This is allowed but unusual."
                )
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def get_constrained_products(self):
        """
        Get all products that match this constraint
        
        Returns:
            product.product recordset
        """
        self.ensure_one()
        
        if self.constraint_type == 'product':
            return self.product_ids
        
        elif self.constraint_type == 'category':
            # Get all products in selected categories
            return self.env['product.product'].search([
                ('categ_id', 'in', self.category_ids.ids)
            ])
        
        else:
            # Unknown type - return empty
            return self.env['product.product']
    
    def check_product_matches(self, product):
        """
        Check if a product matches this constraint
        
        Args:
            product: product.product record
        
        Returns:
            bool: True if product is constrained by this record
        """
        self.ensure_one()
        
        if self.constraint_type == 'product':
            return product in self.product_ids
        
        elif self.constraint_type == 'category':
            return product.categ_id in self.category_ids
        
        return False
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_view_products(self):
        """View all products matching this constraint"""
        self.ensure_one()
        
        products = self.get_constrained_products()
        
        return {
            'name': _('Products: %s') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'product.product',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', products.ids)],
            'context': {'create': False},
        }