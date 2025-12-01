# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """Main Deal Management Model - AUTONOMOUS
    
    Phase 0: Enhanced with sub-deal architecture (1:1 relationship)
    Commercial header encapsulating execution via sub-deals.
    
    Architecture:
    - Deal = Commercial header (customer PO, terms, planning)
    - Subdeal = Execution layer (lines, SO/PO, milestones, shipment)
    
    State Management (Option A):
    - Deal-only states: draft, validated, completed, cancelled
    - Subdeal-synced states: confirmed, in_production, ready, shipped, delivered
    """
    _name = 'dm.deal'
    _description = 'Deal Management'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dm.cascade.mixin']
    _order = 'id desc'
    _rec_name = 'name'
    
    # =========================================================================
    # CORE FIELDS
    # =========================================================================
    
    name = fields.Char(
        string='Deal Reference',
        readonly=True,
        copy=False,
        index=True,
        default='New'
    )
    
    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        tracking=True,
        domain=[('is_company', '=', True)],
        readonly="state not in ['draft']"
    )
    
    customer_po_number = fields.Char(
        string='Customer PO#',
        required=True,
        tracking=True,
        help='Customer Purchase Order Number - Required for all deals',
        readonly="state not in ['draft']"
    )
    
    po_date = fields.Date(
        string='PO Date',
        required=True,
        default=fields.Date.today,
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        tracking=True,
        domain=[('is_company', '=', True), ('supplier_rank', '>', 0)],
        readonly="state not in ['draft']"
    )
    
    template_id = fields.Many2one(
        'dm.deal.template',
        string='Deal Template',
        readonly="state not in ['draft']"
    )
    
    template_selection_pending = fields.Boolean(
        string='Template Selection Pending',
        default=False,
        help='True when multiple templates match and wizard should open'
    )
    
    # =========================================================================
    # INVOICE SPLIT CONFIGURATION
    # =========================================================================
    
    invoice_split = fields.Boolean(
        string='Split Invoice',
        default=True,
        tracking=True,
        help='Split into product invoice and service invoice'
    )
    
    product_invoice_percentage = fields.Float(
        string='Product Invoice %',
        default=85.0,
        digits=(5, 2),
        tracking=True,
        help='Percentage of total to invoice as product (rest is service)'
    )
    
    service_invoice_percentage = fields.Float(
        string='Service Invoice %',
        compute='_compute_service_percentage',
        store=True,
        digits=(5, 2)
    )
    
    @api.depends('product_invoice_percentage')
    def _compute_service_percentage(self):
        for deal in self:
            deal.service_invoice_percentage = 100.0 - deal.product_invoice_percentage
    
    # =========================================================================
    # STATE MANAGEMENT (Option A: Stored, not computed)
    # =========================================================================
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('confirmed', 'Confirmed'),
        ('in_production', 'In Production'),
        ('ready', 'Ready to Ship'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True, tracking=True)
    
    state_sequence = fields.Integer(
        string='State Sequence',
        compute='_compute_state_sequence',
        store=True,
        help='Numeric sequence for proper state ordering in Kanban'
    )
    
    state_display = fields.Char(
        string='State Display',
        compute='_compute_state_sequence',
        store=True,
        help='State name with sequence prefix for proper Kanban ordering'
    )
    
    @api.depends('state')
    def _compute_state_sequence(self):
        """Map states to numeric sequence for proper ordering"""
        STATE_ORDER = {
            'draft': (10, 'Draft'),
            'validated': (20, 'Validated'),
            'confirmed': (30, 'Confirmed'),
            'in_production': (40, 'In Production'),
            'ready': (50, 'Ready to Ship'),
            'shipped': (60, 'Shipped'),
            'delivered': (70, 'Delivered'),
            'completed': (80, 'Completed'),
            'cancelled': (90, 'Cancelled'),
        }
        for deal in self:
            seq, display = STATE_ORDER.get(deal.state, (999, 'Unknown'))
            deal.state_sequence = seq
            deal.state_display = f"{seq:02d} - {display}"
    
    # =========================================================================
    # FIELD LOCKING LOGIC (State-Based Only)
    # =========================================================================
    
    lines_readonly = fields.Boolean(
        compute='_compute_readonly_fields',
        store=False,
        help="Lock lines after confirmation"
    )
    
    prices_readonly = fields.Boolean(
        compute='_compute_readonly_fields',
        store=False,
        help="Lock prices after confirmation"
    )
    
    customer_readonly = fields.Boolean(
        compute='_compute_readonly_fields',
        store=False,
        help="Lock customer after confirmation"
    )
    
    vendor_readonly = fields.Boolean(
        compute='_compute_readonly_fields',
        store=False,
        help="Lock vendor after confirmation"
    )
    
    dates_readonly = fields.Boolean(
        compute='_compute_readonly_fields',
        store=False,
        help="Lock commercial dates after confirmation"
    )
    
    @api.depends('state')
    def _compute_readonly_fields(self):
        """Compute field lock status based on deal state"""
        lock_states = ['confirmed', 'completed']
        
        for deal in self:
            is_locked = deal.state in lock_states
            deal.lines_readonly = is_locked
            deal.prices_readonly = is_locked
            deal.customer_readonly = is_locked
            deal.vendor_readonly = is_locked
            deal.dates_readonly = is_locked
    
    # =========================================================================
    # SMART BUTTON COUNTS
    # =========================================================================
    
    sale_order_count = fields.Integer(
        compute='_compute_order_counts',
        string='Sales Order Count'
    )
    
    purchase_order_count = fields.Integer(
        compute='_compute_order_counts',
        string='Purchase Order Count'
    )
    
    @api.depends('sale_order_ids', 'purchase_order_ids')
    def _compute_order_counts(self):
        """Compute counts for smart buttons"""
        for deal in self:
            deal.sale_order_count = len(deal.sale_order_ids)
            deal.purchase_order_count = len(deal.purchase_order_ids)
    
    # Validation & Confirmation tracking
    validation_date = fields.Date(
        string='Validation Date',
        readonly=True,
        tracking=True,
        help='Date when deal was validated (data completeness check)'
    )
    
    confirmation_date = fields.Date(
        string='Confirmation Date',
        readonly=True,
        tracking=True,
        help='Date when deal was confirmed (SO/PO created and confirmed)'
    )
    
    # SO/PO confirmation status
    so_confirmed = fields.Boolean(
        string='SO Confirmed',
        compute='_compute_confirmation_status',
        store=True
    )
    
    po_confirmed = fields.Boolean(
        string='PO Confirmed',
        compute='_compute_confirmation_status',
        store=True
    )
    
    confirmation_status_display = fields.Char(
        string='Confirmation Status',
        compute='_compute_confirmation_status',
        store=True
    )
    
    @api.depends('sale_order_ids', 'sale_order_ids.state', 'purchase_order_ids', 'purchase_order_ids.state')
    def _compute_confirmation_status(self):
        """Compute SO/PO confirmation status"""
        for deal in self:
            deal.so_confirmed = any(
                so.state in ['sale', 'done'] for so in deal.sale_order_ids
            )
            deal.po_confirmed = any(
                po.state in ['purchase', 'done'] for po in deal.purchase_order_ids
            )
            
            if deal.so_confirmed and deal.po_confirmed:
                deal.confirmation_status_display = 'SO ✓ PO ✓'
            elif deal.so_confirmed:
                deal.confirmation_status_display = 'SO ✓ PO ✗'
            elif deal.po_confirmed:
                deal.confirmation_status_display = 'SO ✗ PO ✓'
            else:
                deal.confirmation_status_display = 'SO ✗ PO ✗'
    
    # =========================================================================
    # RELATIONAL FIELDS - SO/PO/LINES
    # =========================================================================
    
    # Display helper - products in this deal
    product_ids = fields.Many2many(
        'product.product',
        string='Products',
        compute='_compute_product_ids',
        store=False,
        help='Products included in this deal (for display/filtering)'
    )
    
    @api.depends('line_ids', 'line_ids.product_id')
    def _compute_product_ids(self):
        """Compute unique products from deal lines"""
        for deal in self:
            deal.product_ids = deal.line_ids.mapped('product_id')
    
    # =========================================================================
    # SALES TERMS
    # =========================================================================
    
    sale_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Customer Payment Terms',
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    sale_incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Customer Incoterm',
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    sale_incoterm_location = fields.Char(
        string='Customer Incoterm Location',
        readonly="state not in ['draft']"
    )
    
    # =========================================================================
    # PURCHASE TERMS
    # =========================================================================
    
    purchase_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Vendor Payment Terms',
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    purchase_incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Vendor Incoterm',
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    purchase_incoterm_location = fields.Char(
        string='Vendor Incoterm Location',
        readonly="state not in ['draft']"
    )
    
    # =========================================================================
    # LOGISTICS
    # =========================================================================
    
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Loading Port',
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Discharge Port',
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    # =========================================================================
    # CURRENCY
    # =========================================================================
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
        readonly="state not in ['draft']"
    )
    
    # =========================================================================
    # COMPANY
    # =========================================================================
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # =========================================================================
    # MILESTONE DATES (Three-Layer Pattern)
    # Note: Additional milestone logic in dm_deal_milestones.py
    # =========================================================================
    
    production_start_requested = fields.Date(string='Production Start (Requested)')
    production_start_current = fields.Date(string='Production Start (Current)')
    production_start_actual = fields.Date(string='Production Start (Actual)', readonly=True)
    
    rts_requested = fields.Date(string='RTS (Requested)')
    rts_current = fields.Date(string='RTS (Current)')
    rts_actual = fields.Date(string='RTS (Actual)', readonly=True)
    
    loading_requested = fields.Date(string='Loading (Requested)')
    loading_current = fields.Date(string='Loading (Current)')
    loading_actual = fields.Date(string='Loading (Actual)', readonly=True)
    
    etd_requested = fields.Date(string='ETD (Requested)')
    etd_current = fields.Date(string='ETD (Current)')
    etd_actual = fields.Date(string='ETD (Actual)', readonly=True)
    
    eta_requested = fields.Date(string='ETA (Requested)')
    eta_current = fields.Date(string='ETA (Current)')
    eta_actual = fields.Date(string='ETA (Actual)', readonly=True)
    
    delivery_requested = fields.Date(string='Delivery (Requested)')
    delivery_current = fields.Date(string='Delivery (Current)')
    delivery_actual = fields.Date(string='Delivery (Actual)', readonly=True)
    
    # =========================================================================
    # COMPUTED TOTALS
    # =========================================================================
    
    total_quantity = fields.Float(
        compute='_compute_totals',
        string='Total Quantity (Packages)',
        store=True
    )
    
    amount_untaxed_sale = fields.Monetary(
        compute='_compute_totals',
        string='Total Sale Amount',
        store=True,
        currency_field='currency_id'
    )
    
    amount_untaxed_purchase = fields.Monetary(
        compute='_compute_totals',
        string='Total Purchase Amount',
        store=True,
        currency_field='currency_id'
    )
    
    margin = fields.Monetary(
        compute='_compute_totals',
        string='Margin',
        store=True,
        currency_field='currency_id'
    )
    
    margin_percent = fields.Float(
        compute='_compute_totals',
        string='Margin %',
        store=True
    )
    
    total_containers = fields.Float(
        compute='_compute_totals',
        string='Total Containers',
        store=True
    )
    
    total_teu = fields.Float(
        compute='_compute_totals',
        string='Total TEU',
        store=True
    )
    
    @api.depends('line_ids.quantity_packaging', 'line_ids.amount_sale',
                 'line_ids.amount_purchase', 'line_ids.containers_required',
                 'line_ids.container_teu')
    def _compute_totals(self):
        """Compute deal totals from lines"""
        for deal in self:
            deal.total_quantity = sum(deal.line_ids.mapped('quantity_packaging'))
            deal.amount_untaxed_sale = sum(deal.line_ids.mapped('amount_sale'))
            deal.amount_untaxed_purchase = sum(deal.line_ids.mapped('amount_purchase'))
            deal.margin = deal.amount_untaxed_sale - deal.amount_untaxed_purchase
            
            if deal.amount_untaxed_sale > 0:
                deal.margin_percent = (deal.margin / deal.amount_untaxed_sale) * 100
            else:
                deal.margin_percent = 0.0
            
            # Container totals
            deal.total_containers = sum(deal.line_ids.mapped('containers_required'))
            deal.total_teu = sum(deal.line_ids.mapped('container_teu'))
    
    # =========================================================================
    # SUB-DEALS (Phase 0: 1:1 relationship)
    # =========================================================================
    
    subdeal_ids = fields.One2many(
        'dm.deal.subdeal',
        'deal_id',
        string='Sub-Deals'
    )
    
    subdeal_count = fields.Integer(
        string='# Sub-Deals',
        compute='_compute_subdeal_count',
        store=True
    )
    
    primary_subdeal_id = fields.Many2one(
        'dm.deal.subdeal',
        string='Primary Sub-Deal',
        compute='_compute_primary_subdeal',
        store=True,
        help='Single sub-deal in Phase 0 (1:1 relationship)'
    )
    
    @api.depends('subdeal_ids')
    def _compute_subdeal_count(self):
        for deal in self:
            deal.subdeal_count = len(deal.subdeal_ids)
    
    @api.depends('subdeal_ids')
    def _compute_primary_subdeal(self):
        """Get the single sub-deal (Phase 0)"""
        for deal in self:
            deal.primary_subdeal_id = deal.subdeal_ids[:1]
    
    def _create_primary_subdeal(self):
        """Create the primary subdeal (Phase 0)"""
        self.ensure_one()
        
        if self.subdeal_ids:
            _logger.warning(f"Deal {self.name} already has subdeal, skipping creation")
            return self.primary_subdeal_id
        
        subdeal = self.env['dm.deal.subdeal'].create({
            'deal_id': self.id,
            'name': 'Shipment',
            'sequence': 10,
        })
        
        _logger.info(f"Created primary subdeal {subdeal.id} for deal {self.name}")
        return subdeal
    
    # Shipment allocation (delegated from subdeal)
    shipment_allocated = fields.Boolean(
        string='Allocated to Shipment',
        compute='_compute_shipment_allocated',
        store=True
    )
    
    @api.depends('primary_subdeal_id.shipment_allocated')
    def _compute_shipment_allocated(self):
        for deal in self:
            deal.shipment_allocated = deal.primary_subdeal_id.shipment_allocated if deal.primary_subdeal_id else False
    
    # =========================================================================
    # CRUD OVERRIDES
    # =========================================================================
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('dm.deal') or 'New'
        
        deal = super().create(vals)
        
        if deal.line_ids and not deal.template_id:
            deal._apply_template_from_lines()
        
        return deal
    
    def write(self, vals):
        # Date cascade logging (delegated to milestones mixin)
        for deal in self:
            if 'rts_current' in vals and vals['rts_current'] != deal.rts_current:
                if hasattr(deal, 'cascade_date_change'):
                    deal.cascade_date_change('rts_current', deal.rts_current, vals['rts_current'])
        
        res = super().write(vals)
        
        # Auto-confirmation check
        if not vals.get('state') and not self._context.get('skip_auto_confirm_check'):
            self._check_auto_confirmation()
        
        return res
    
    def _check_auto_confirmation(self):
        """Auto-confirm deal when both SO and PO are confirmed"""
        for deal in self:
            if deal.state == 'validated' and deal.so_confirmed and deal.po_confirmed:
                deal.state = 'confirmed'
                _logger.info(f"Deal {deal.name} auto-confirmed (SO+PO confirmed)")
    
    def _apply_template_from_lines(self):
        """Apply template based on line products - stub for extension"""
        pass