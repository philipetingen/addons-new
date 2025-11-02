from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """Main Deal Management Model - CORE
    
    File restructuring v3.0:
    - Merged state machine from dm_deal_state_machine.py
    - Added 'partial' and 'completed' states
    - Refined state machine for Phase 4B
    - Core fields and state management only
    - Extensions in domain-specific files
    """
    _name = 'dm.deal'
    _description = 'Deal Management'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dm.cascade.mixin']
    _order = 'id desc'
    _rec_name = 'name'
    
    # ============================================================
    # CORE FIELDS
    # ============================================================
    
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
    
    # ============================================================
    # STATE MANAGEMENT - REFINED FOR PHASE 4B
    # ============================================================
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('confirmed', 'Confirmed'),
        ('partial', 'Partial Allocation'),
        ('allocated', 'Allocated'),
        ('ready', 'Ready to Ship'),
        ('shipping', 'Shipping'),
        ('delivered', 'Delivered'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True, tracking=True)

    # =======================================================================
    # FIELD LOCKING LOGIC (Phase 4B Step 1)
    # =======================================================================

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
        """
        Compute field lock status based on deal state.
        
        Lock Rules:
        - Lines: Lock at confirmed (committed to customer)
        - Prices: Lock at confirmed (commercial commitment)
        - Customer: Lock at confirmed (can't change who deal is for)
        - Vendor: Lock at confirmed (can't change supplier)
        - Dates: Lock at confirmed (committed delivery schedule)
        
        Production dates (rts_current, rts_actual) remain editable during production
        via CASCADE overrides.
        """
        lock_states = [
            'confirmed', 'partial', 'allocated', 
            'ready', 'shipping', 'delivered', 'completed'
        ]
        
        for deal in self:
            is_locked = deal.state in lock_states
            deal.lines_readonly = is_locked
            deal.prices_readonly = is_locked
            deal.customer_readonly = is_locked
            deal.vendor_readonly = is_locked
            deal.dates_readonly = is_locked

    # =======================================================================
    # SMART BUTTON COUNTS (Phase 4B Step 1)
    # =======================================================================

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

    # ============================================================
    # DEAL LOCKING MECHANISM
    # ============================================================
    
    is_locked_for_production = fields.Boolean(
        compute='_compute_production_lock',
        store=True,
        string='Locked by Production',
        help='Deal locked due to active production allocation'
    )
    
    is_locked_for_shipment = fields.Boolean(
        compute='_compute_shipment_lock',
        store=True,
        string='Locked by Shipment',
        help='Deal locked due to active shipment allocation'
    )
    
    production_lock_reason = fields.Char(
        compute='_compute_production_lock',
        string='Production Lock Reason',
        help='Production run causing the lock'
    )
    
    shipment_lock_reason = fields.Char(
        compute='_compute_shipment_lock',
        string='Shipment Lock Reason',
        help='Shipment causing the lock'
    )
    
    # ============================================================
    # MILESTONE MATRIX - THREE-LAYER DATES
    # ============================================================
    
    # Milestone 1: Order Confirmation (uses confirmation_date)
    
    # Milestone 2: Production Start
    production_start_requested = fields.Date(
        string='Production Start Requested',
        tracking=True,
        help='Original requested production start date'
    )
    production_start_current = fields.Date(
        string='Production Start Current',
        tracking=True,
        help='Current planned production start date'
    )
    production_start_actual = fields.Date(
        string='Production Start Actual',
        readonly=True,
        tracking=True,
        help='Actual production start date (set by production module)'
    )
    production_start_calculated = fields.Date(
        string='Calculated Production Start',
        compute='_compute_production_start_calculated',
        store=True,
        help='Auto-calculated: RTS - Production Cycle Time'
    )
    
    # Milestone 3: Ready to Ship (RTS)
    rts_requested = fields.Date(
        string='RTS Requested',
        help='Ready to Ship date requested by customer',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    rts_current = fields.Date(
        string='RTS Current',
        help='Negotiated Ready to Ship date',
        tracking=True
    )
    rts_actual = fields.Date(
        string='RTS Actual',
        help='Actual Ready to Ship date',
        readonly=True,
        tracking=True
    )
    
    # Milestone 4: Loading
    loading_requested = fields.Date(
        string='Loading Requested',
        tracking=True,
        help='Requested loading date at factory'
    )
    loading_current = fields.Date(
        string='Loading Current',
        tracking=True,
        help='Current planned loading date'
    )
    loading_actual = fields.Date(
        string='Loading Actual',
        readonly=True,
        tracking=True,
        help='Actual loading date (set by shipment module)'
    )
    
    # Milestone 5: ETD (Estimated Time of Departure)
    etd_requested = fields.Date(
        string='ETD Requested',
        tracking=True,
        help='Requested vessel departure date'
    )
    etd_current = fields.Date(
        string='ETD Current',
        tracking=True,
        help='Current estimated departure date'
    )
    etd_actual = fields.Date(
        string='ETD Actual',
        readonly=True,
        tracking=True,
        help='Actual departure date (set by shipment module)'
    )
    
    # Milestone 6: ETA (Estimated Time of Arrival)
    eta_requested = fields.Date(
        string='ETA Requested',
        help='Arrival date requested by customer',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    eta_current = fields.Date(
        string='ETA Current',
        help='Current estimated arrival date',
        tracking=True
    )
    eta_actual = fields.Date(
        string='ETA Actual',
        help='Actual arrival date',
        readonly=True,
        tracking=True
    )
    
    # Milestone 7: Delivery
    delivery_requested = fields.Date(
        string='Delivery Requested',
        tracking=True,
        help='Requested final delivery date to customer'
    )
    delivery_current = fields.Date(
        string='Delivery Current',
        tracking=True,
        help='Current planned delivery date'
    )
    delivery_actual = fields.Date(
        string='Delivery Actual',
        readonly=True,
        tracking=True,
        help='Actual delivery date to customer'
    )
    
    # ============================================================
    # COMMERCIAL TERMS
    # ============================================================
    
    # SALES Commercial Terms
    sale_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Sales Payment Terms',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']",
        help='Payment terms for customer'
    )
    
    sale_incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Sales Incoterm',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']",
        help='Delivery terms for customer'
    )
    
    sale_incoterm_location = fields.Char(
        string='Sales Delivery Location',
        readonly="state not in ['draft', 'confirmed']"
    )
    
    # PURCHASE Commercial Terms
    purchase_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Purchase Payment Terms',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']",
        help='Payment terms for supplier'
    )
    
    purchase_incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Purchase Incoterm',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']",
        help='Delivery terms from supplier'
    )
    
    purchase_incoterm_location = fields.Char(
        string='Purchase Delivery Location',
        readonly="state not in ['draft', 'confirmed']"
    )
    
    # Backward compatibility
    payment_term_id = fields.Many2one(
        'account.payment.term',
        compute='_compute_payment_term_backward',
        readonly=True,
        store=False
    )
    
    incoterm_id = fields.Many2one(
        'account.incoterms',
        compute='_compute_incoterm_backward',
        readonly=True,
        store=False
    )
    
    incoterm_location = fields.Char(
        compute='_compute_incoterm_location_backward',
        readonly=True,
        store=False
    )
    
    # Ports
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Port of Loading (POL)',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Port of Discharge (POD)',
        tracking=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    
    # ============================================================
    # FINANCIAL
    # ============================================================
    
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.ref('base.USD', raise_if_not_found=False) or self.env.company.currency_id,
        required=True,
        readonly="state not in ['draft']"
    )
    
    company_currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        string='Company Currency',
        readonly=True
    )
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
        required=True
    )
    
    # Invoice Split
    invoice_split = fields.Boolean(
        string='Split Invoice',
        default=True,
        help='Split into product and service invoices',
        readonly="state not in ['draft']"
    )
    
    product_invoice_percentage = fields.Float(
        string='Product Invoice %',
        default=85.0,
        digits=(5, 2),
        readonly="state not in ['draft']"
    )
    
    service_invoice_percentage = fields.Float(
        string='Service Invoice %',
        compute='_compute_service_percentage',
        store=True,
        digits=(5, 2)
    )
    
    # ============================================================
    # LINES
    # ============================================================
    
    line_ids = fields.One2many(
        'dm.deal.line',
        'deal_id',
        string='Deal Lines',
        copy=True,
        readonly="state not in ['draft', 'confirmed']"
    )
    
    # ============================================================
    # ALLOCATION RELATIONSHIPS
    # ============================================================
    
    allocation_ids = fields.One2many(
        'dm.allocation',
        'deal_id',
        string='Allocations'
    )
    
    allocation_status = fields.Selection([
        ('unallocated', 'Not Allocated'),
        ('partial', 'Partially Allocated'),
        ('allocated', 'Fully Allocated')
    ], compute='_compute_allocation_status', store=True, string='Allocation Status')
    
    allocation_count = fields.Integer(
        string='Allocation Count',
        compute='_compute_allocation_counts',
        store=True
    )
    
    # ============================================================
    # SO/PO REFERENCES
    # ============================================================
    
    sale_order_ids = fields.One2many(
        'sale.order',
        'dm_deal_id',
        string='Sales Orders'
    )
    
    purchase_order_ids = fields.One2many(
        'purchase.order',
        'dm_deal_id',
        string='Purchase Orders'
    )
    
    # ============================================================
    # COMPUTED TOTALS
    # ============================================================
    
    total_sale_amount = fields.Float(
        string='Total Sale Amount',
        compute='_compute_totals',
        store=True,
        digits=(16, 2)
    )
    
    total_purchase_amount = fields.Float(
        string='Total Purchase Amount',
        compute='_compute_totals',
        store=True,
        digits=(16, 2)
    )
    
    margin_amount = fields.Float(
        string='Margin Amount',
        compute='_compute_totals',
        store=True,
        digits=(16, 2)
    )
    
    margin_percentage = fields.Float(
        string='Margin %',
        compute='_compute_totals',
        store=True,
        digits=(5, 2)
    )
    
    # ============================================================
    # CONTAINER TOTALS
    # ============================================================
    
    total_containers = fields.Float(
        string='Total Containers',
        compute='_compute_container_totals',
        store=True,
        digits=(16, 3),
        help='Sum of all line container requirements'
    )
    
    total_teu = fields.Float(
        string='Total TEU',
        compute='_compute_container_totals',
        store=True,
        digits=(16, 2),
        help='Total twenty-foot equivalent units'
    )
    
    # ============================================================
    # QUANTITY SUMMARIES (Phase 4B Step 2)
    # ============================================================
    
    total_quantity_ordered = fields.Float(
        string='Total Ordered',
        compute='_compute_quantity_totals',
        store=True,
        digits=(16, 3),
        help="Sum of ordered quantities across all lines"
    )
    
    total_quantity_produced = fields.Float(
        string='Total Produced',
        compute='_compute_quantity_totals',
        store=True,
        digits=(16, 3),
        help="Sum of produced quantities across all lines"
    )
    
    total_quantity_loaded = fields.Float(
        string='Total Loaded',
        compute='_compute_quantity_totals',
        store=True,
        digits=(16, 3),
        help="Sum of loaded quantities across all lines"
    )
    
    quantity_completion_rate = fields.Float(
        string='Completion Rate %',
        compute='_compute_quantity_totals',
        store=True,
        digits=(5, 2),
        help="Percentage of ordered quantity that was loaded"
    )
    
    container_summary = fields.Char(
        string='Container Summary',
        compute='_compute_container_summary',
        help='Human-readable container summary'
    )
    
    # ============================================================
    # COUNTS FOR SMART BUTTONS
    # ============================================================

    so_count = fields.Integer(compute='_compute_counts', string='SO Count')
    po_count = fields.Integer(compute='_compute_counts', string='PO Count')

    # ============================================================
    # UNIVERSAL DEAL FIELDS MIXIN
    # ============================================================

    product_ids = fields.Many2many(
        'product.product',
        compute='_compute_product_ids',
        store=True,
        string='Products'
    )
    
    # ============================================================
    # COMPUTED METHODS - BASIC
    # ============================================================
    
    @api.depends('line_ids', 'line_ids.product_id')
    def _compute_product_ids(self):
        """Compute unique products from deal lines, sorted by category."""
        for deal in self:
            if not deal.line_ids:
                deal.product_ids = False
                continue
            
            lines_with_products = deal.line_ids.filtered(lambda l: l.product_id)
            
            if not lines_with_products:
                deal.product_ids = False
                continue
            
            products = lines_with_products.mapped('product_id')
            
            sorted_products = products.sorted(
                key=lambda p: (
                    p.categ_id.display_sequence if p.categ_id and hasattr(p.categ_id, 'display_sequence') else 9999,
                    p.name or ''
                )
            )
            
            deal.product_ids = sorted_products

    def get_milestone_date(self, milestone_code, prefer='best'):
        """
        Get milestone date with fallback logic.
        CRITICAL: Single source of truth for milestone dates.
        
        Args:
            milestone_code: 'order_conf', 'prod_start', 'rts', 'loading', 
                           'etd', 'eta', 'delivery'
            prefer: 'actual', 'current', 'requested', or 'best' (auto-select)
        
        Returns:
            Date or False
        """
        self.ensure_one()
        
        mapping = {
            'order_conf': (self.confirmation_date, self.confirmation_date, self.confirmation_date),
            'prod_start': (self.production_start_requested, self.production_start_current or self.production_start_calculated, self.production_start_actual),
            'rts': (self.rts_requested, self.rts_current, self.rts_actual),
            'loading': (self.loading_requested, self.loading_current, self.loading_actual),
            'etd': (self.etd_requested, self.etd_current, self.etd_actual),
            'eta': (self.eta_requested, self.eta_current, self.eta_actual),
            'delivery': (self.delivery_requested, self.delivery_current, self.delivery_actual),
        }
        
        dates = mapping.get(milestone_code)
        if not dates:
            _logger.warning(f"Unknown milestone code: {milestone_code}")
            return False
        
        requested, current, actual = dates
        
        if prefer == 'actual':
            return actual
        elif prefer == 'current':
            return current or requested
        elif prefer == 'requested':
            return requested
        else:  # 'best'
            return actual or current or requested

    @api.depends('sale_payment_term_id')
    def _compute_payment_term_backward(self):
        for deal in self:
            deal.payment_term_id = deal.sale_payment_term_id
    
    @api.depends('sale_incoterm_id')
    def _compute_incoterm_backward(self):
        for deal in self:
            deal.incoterm_id = deal.sale_incoterm_id
    
    @api.depends('sale_incoterm_location')
    def _compute_incoterm_location_backward(self):
        for deal in self:
            deal.incoterm_location = deal.sale_incoterm_location

    @api.depends('rts_current', 'rts_requested', 'line_ids.product_id.total_production_cycle', 'production_start_requested')
    def _compute_production_start_calculated(self):
        """Calculate production start date from RTS minus production cycle"""
        for deal in self:
            if deal.production_start_requested:
                deal.production_start_calculated = deal.production_start_requested
                continue
            
            rts_date = deal.rts_current or deal.rts_requested
            
            if rts_date and deal.line_ids:
                max_cycle = max(
                    (line.product_id.total_production_cycle or 21)
                    for line in deal.line_ids
                )
                deal.production_start_calculated = rts_date - timedelta(days=max_cycle)
            else:
                deal.production_start_calculated = False

    @api.depends('sale_order_ids.state', 'purchase_order_ids.state')
    def _compute_confirmation_status(self):
        """Track SO/PO confirmation status"""
        for deal in self:
            if deal.sale_order_ids:
                deal.so_confirmed = any(
                    so.state in ['sale', 'done'] 
                    for so in deal.sale_order_ids
                )
            else:
                deal.so_confirmed = False
            
            if deal.purchase_order_ids:
                deal.po_confirmed = any(
                    po.state in ['purchase', 'done']
                    for po in deal.purchase_order_ids
                )
            else:
                deal.po_confirmed = False if deal.supplier_id else True
            
            so_status = '✓ SO' if deal.so_confirmed else '○ SO'
            po_status = '✓ PO' if deal.po_confirmed else '○ PO'
            deal.confirmation_status_display = f"{so_status} | {po_status}"
    
    @api.depends('allocation_ids.state', 'allocation_ids.allocation_type')
    def _compute_production_lock(self):
        """Check if deal is locked by production allocation"""
        for deal in self:
            pr_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'production' and a.state == 'active'
            )
            
            if pr_allocs and hasattr(pr_allocs[0], 'production_run_id'):
                pr = pr_allocs[0].production_run_id
                if pr and pr.state in ['confirmed', 'production', 'ready']:
                    deal.is_locked_for_production = True
                    deal.production_lock_reason = f"PR-{pr.name} ({pr.state})"
                else:
                    deal.is_locked_for_production = False
                    deal.production_lock_reason = False
            else:
                deal.is_locked_for_production = False
                deal.production_lock_reason = False
    
    @api.depends('allocation_ids.state', 'allocation_ids.allocation_type')
    def _compute_shipment_lock(self):
        """Check if deal is locked by shipment allocation"""
        for deal in self:
            ship_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'shipment' and a.state == 'active'
            )
            
            if ship_allocs and hasattr(ship_allocs[0], 'shipment_id'):
                ship = ship_allocs[0].shipment_id
                if ship and ship.state in ['confirmed', 'loading', 'shipped', 'arrived']:
                    deal.is_locked_for_shipment = True
                    deal.shipment_lock_reason = f"SHIP-{ship.name} ({ship.state})"
                else:
                    deal.is_locked_for_shipment = False
                    deal.shipment_lock_reason = False
            else:
                deal.is_locked_for_shipment = False
                deal.shipment_lock_reason = False
    
    @api.depends('product_invoice_percentage')
    def _compute_service_percentage(self):
        for deal in self:
            deal.service_invoice_percentage = 100.0 - deal.product_invoice_percentage
    
    @api.depends('line_ids.amount_sale', 'line_ids.amount_purchase')
    def _compute_totals(self):
        for deal in self:
            deal.total_sale_amount = sum(deal.line_ids.mapped('amount_sale'))
            deal.total_purchase_amount = sum(deal.line_ids.mapped('amount_purchase'))
            deal.margin_amount = deal.total_sale_amount - deal.total_purchase_amount
            if deal.total_sale_amount:
                deal.margin_percentage = (deal.margin_amount / deal.total_sale_amount) * 100
            else:
                deal.margin_percentage = 0.0
    
    @api.depends('line_ids.containers_required', 'line_ids.container_teu')
    def _compute_container_totals(self):
        for deal in self:
            deal.total_containers = sum(deal.line_ids.mapped('containers_required'))
            deal.total_teu = sum(deal.line_ids.mapped('container_teu'))
    
    @api.depends('line_ids.quantity_packaging', 
                 'line_ids.quantity_produced',
                 'line_ids.quantity_loaded')
    def _compute_quantity_totals(self):
        """Compute deal-level quantity summaries"""
        for deal in self:
            deal.total_quantity_ordered = sum(deal.line_ids.mapped('quantity_packaging'))
            deal.total_quantity_produced = sum(deal.line_ids.mapped('quantity_produced'))
            deal.total_quantity_loaded = sum(deal.line_ids.mapped('quantity_loaded'))
            
            if deal.total_quantity_ordered:
                deal.quantity_completion_rate = (
                    (deal.total_quantity_loaded / deal.total_quantity_ordered) * 100
                )
            else:
                deal.quantity_completion_rate = 0.0
    
    @api.depends('line_ids.container_type_id', 'line_ids.containers_required')
    def _compute_container_summary(self):
        for deal in self:
            if not deal.line_ids:
                deal.container_summary = 'No containers'
                continue
            
            container_dict = {}
            for line in deal.line_ids:
                if line.container_type_id and line.containers_required > 0:
                    ct_name = line.container_type_id.name
                    container_dict[ct_name] = container_dict.get(ct_name, 0) + line.containers_required
            
            if container_dict:
                summary_parts = [f"{qty:.1f}× {ct}" for ct, qty in container_dict.items()]
                deal.container_summary = ', '.join(summary_parts)
            else:
                deal.container_summary = 'No containers'
    
    @api.depends('sale_order_ids', 'purchase_order_ids')
    def _compute_counts(self):
        for deal in self:
            deal.so_count = len(deal.sale_order_ids)
            deal.po_count = len(deal.purchase_order_ids)
    
    @api.depends('allocation_ids.state')
    def _compute_allocation_counts(self):
        for deal in self:
            deal.allocation_count = len(deal.allocation_ids.filtered(lambda a: a.state == 'active'))
    
    @api.depends('allocation_ids.state', 'allocation_ids.allocation_type')
    def _compute_allocation_status(self):
        for deal in self:
            active_allocs = deal.allocation_ids.filtered(lambda a: a.state == 'active')
            
            if not active_allocs:
                deal.allocation_status = 'unallocated'
            else:
                has_production = any(a.allocation_type == 'production' for a in active_allocs)
                has_shipment = any(a.allocation_type == 'shipment' for a in active_allocs)
                
                if has_production and has_shipment:
                    deal.allocation_status = 'allocated'
                else:
                    deal.allocation_status = 'partial'
    
    # ============================================================
    # STATE MACHINE - MERGED FROM dm_deal_state_machine.py
    # ============================================================
    
    @api.depends('allocation_ids.state', 'allocation_ids.allocation_type', 'sale_order_ids', 'purchase_order_ids')
    def _compute_deal_state_from_allocations(self):
        """
        Auto-compute deal state based on allocation progress.
        
        State Priority Hierarchy:
        1. delivered (shipment delivered) - AUTO
        2. shipping (shipment shipped/arrived) - AUTO
        3. ready (production ready, shipment < shipped) - AUTO
        4. allocated (has PR + Ship) - AUTO
        5. partial (has PR OR Ship) - AUTO
        6. confirmed (SO/PO confirmed) - AUTO
        7. validated (SO/PO exists) - AUTO
        8. draft (initial) - AUTO
        
        Does NOT override: completed, cancelled (manual states)
        """
        for deal in self:
            # Skip manually set final states
            if deal.state in ['completed', 'cancelled']:
                continue
            
            # Get active/completed allocations
            pr_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'production' 
                and a.state in ['active', 'completed']
            )
            ship_allocs = deal.allocation_ids.filtered(
                lambda a: a.allocation_type == 'shipment' 
                and a.state in ['active', 'completed']
            )
            
            old_state = deal.state
            new_state = old_state
            
            # Priority 1: Shipment delivered → delivered
            if ship_allocs:
                delivered_ships = [
                    a for a in ship_allocs 
                    if a.shipment_id and a.shipment_id.state == 'delivered'
                ]
                if delivered_ships:
                    new_state = 'delivered'
                    if old_state != new_state:
                        deal.state = new_state
                        _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (shipment delivered)")
                    continue
            
            # Priority 2: Shipment in progress → shipping
            if ship_allocs:
                shipping_states = [
                    a for a in ship_allocs 
                    if a.shipment_id and a.shipment_id.state in ['shipped', 'arrived']
                ]
                if shipping_states:
                    new_state = 'shipping'
                    if old_state != new_state:
                        deal.state = new_state
                        _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (shipment in progress)")
                    continue
            
            # Priority 3: Production ready, shipment not yet shipped → ready
            if pr_allocs:
                ready_prs = [
                    a for a in pr_allocs
                    if a.production_run_id 
                    and a.production_run_id.state in ['ready', 'done']
                ]
                
                if ready_prs and len(ready_prs) == len(pr_allocs):
                    if ship_allocs:
                        not_shipped = all(
                            a.shipment_id.state in ['draft', 'confirmed', 'loading']
                            for a in ship_allocs if a.shipment_id
                        )
                        if not_shipped:
                            new_state = 'ready'
                            if old_state != new_state:
                                deal.state = new_state
                                _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (production ready, shipment not shipped)")
                            continue
                    else:
                        new_state = 'ready'
                        if old_state != new_state:
                            deal.state = new_state
                            _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (production ready, no shipment)")
                        continue
            
            # Priority 4: Has both allocations → allocated
            if pr_allocs and ship_allocs:
                new_state = 'allocated'
                if old_state != new_state:
                    deal.state = new_state
                    _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (has production + shipment)")
                continue
            
            # Priority 5: Has one allocation → partial
            if pr_allocs or ship_allocs:
                new_state = 'partial'
                if old_state != new_state:
                    deal.state = new_state
                    alloc_type = 'production' if pr_allocs else 'shipment'
                    _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (has {alloc_type} only)")
                continue
            
            # Priority 6: SO+PO confirmed → confirmed
            if deal.so_confirmed and deal.po_confirmed:
                new_state = 'confirmed'
                if old_state != new_state:
                    deal.state = new_state
                    _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (SO+PO confirmed)")
                continue
            
            # Priority 7: Has SO or PO → validated
            if deal.sale_order_ids or deal.purchase_order_ids:
                new_state = 'validated'
                if old_state != new_state:
                    deal.state = new_state
                    _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (has SO/PO)")
                continue
            
            # Priority 8: Default → draft
            if old_state not in ['draft', 'validated', 'confirmed']:
                new_state = 'draft'
                if old_state != new_state:
                    deal.state = new_state
                    _logger.info(f"Deal {deal.name}: {old_state} → {new_state} (no allocations or SO/PO)")
    
    def action_complete(self):
        """
        Mark deal as completed (manual closure by manager).
        Can only be done from 'delivered' state.
        """
        for deal in self:
            if deal.state != 'delivered':
                raise UserError(_(
                    'Only delivered deals can be marked as completed.\n\n'
                    'Current state: %s\n'
                    'Please ensure the shipment is delivered first.'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            # Optional: Check for outstanding downpayments
            if hasattr(deal, 'downpayment_request_ids'):
                outstanding_dps = deal.downpayment_request_ids.filtered(
                    lambda dp: dp.state not in ['paid', 'cancelled']
                )
                if outstanding_dps:
                    raise UserError(_(
                        'Cannot complete deal with outstanding downpayment requests.\n\n'
                        'Outstanding requests: %s\n\n'
                        'Please settle or cancel them first.'
                    ) % ', '.join(outstanding_dps.mapped('name')))
            
            # Optional: Check for open activities
            if deal.activity_ids:
                raise UserError(_(
                    'Cannot complete deal with open activities.\n\n'
                    'Please close all activities first.'
                ))
            
            deal.write({'state': 'completed'})
            
            deal.message_post(
                body=_('Deal completed by %s') % self.env.user.name,
                subject=_('Deal Completed'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"Deal {deal.name} marked as completed by {self.env.user.name}")
        
        return True
    
    def action_reopen(self):
        """
        Reopen a completed deal (back to delivered state).
        Manager action only.
        """
        for deal in self:
            if deal.state != 'completed':
                raise UserError(_(
                    'Only completed deals can be reopened.\n\n'
                    'Current state: %s'
                ) % dict(deal._fields['state'].selection).get(deal.state))
            
            deal.write({'state': 'delivered'})
            
            deal.message_post(
                body=_('Deal reopened by %s') % self.env.user.name,
                subject=_('Deal Reopened'),
                message_type='notification',
                subtype_xmlid='mail.mt_note'
            )
            
            _logger.info(f"Deal {deal.name} reopened by {self.env.user.name}")
        
        return True
    
    # ============================================================
    # CRUD OVERRIDES
    # ============================================================
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('dm.deal') or 'New'
        
        deal = super().create(vals)
        
        if deal.line_ids and not deal.template_id:
            deal._apply_template_from_lines()
        
        return deal
    
    def write(self, vals):
        # Lock validation - Production fields
        PRODUCTION_LOCKED = {
            'supplier_id', 'purchase_payment_term_id', 'purchase_incoterm_id',
            'purchase_incoterm_location', 'production_start_requested',
            'rts_requested', 'rts_current', 'currency_id'
        }
        
        # Lock validation - Shipment fields
        SHIPMENT_LOCKED = {
            'loading_port_id', 'discharge_port_id', 'sale_incoterm_id',
            'sale_incoterm_location', 'sale_payment_term_id',
            'customer_po_number', 'loading_requested', 'loading_current',
            'etd_requested', 'etd_current', 'eta_requested', 'eta_current',
            'delivery_requested', 'delivery_current'
        }
        
        for deal in self:
            if deal.is_locked_for_production:
                attempted_pr_changes = set(vals.keys()) & PRODUCTION_LOCKED
                if attempted_pr_changes:
                    raise UserError(_(
                        "Cannot modify production-locked fields while allocated to %s\n\n"
                        "Locked fields: %s\n\n"
                        "To edit: Cancel allocation → Modify deal → Reallocate"
                    ) % (deal.production_lock_reason, ', '.join(attempted_pr_changes)))
            
            if deal.is_locked_for_shipment:
                attempted_ship_changes = set(vals.keys()) & SHIPMENT_LOCKED
                if attempted_ship_changes:
                    raise UserError(_(
                        "Cannot modify shipment-locked fields while allocated to %s\n\n"
                        "Locked fields: %s\n\n"
                        "To edit: Cancel allocation → Modify deal → Reallocate"
                    ) % (deal.shipment_lock_reason, ', '.join(attempted_ship_changes)))
        
        # Date cascade logging
        for deal in self:
            if 'rts_current' in vals and vals['rts_current'] != deal.rts_current:
                if hasattr(deal, 'cascade_date_change'):
                    deal.cascade_date_change('rts_current', deal.rts_current, vals['rts_current'])
        
        res = super().write(vals)
        
        # State-based updates
        if 'state' in vals:
            for deal in self:
                if vals['state'] == 'ready':
                    prod_allocations = deal.allocation_ids.filtered(
                        lambda a: a.allocation_type == 'production' and a.state == 'active'
                    )
                    if prod_allocations:
                        prod_allocations.action_complete()
        
        # Auto-confirmation check
        if not vals.get('state') and not self._context.get('skip_auto_confirm_check'):
            self._check_auto_confirmation()
        
        return res
    
    # ============================================================
    # ONCHANGE METHODS
    # ============================================================
    
    @api.onchange('rts_requested')
    def _onchange_rts_requested(self):
        if self.rts_requested and not self.rts_current:
            self.rts_current = self.rts_requested
    
    @api.onchange('eta_requested')  
    def _onchange_eta_requested(self):
        if self.eta_requested and not self.eta_current:
            self.eta_current = self.eta_requested