from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime, timedelta
import logging

_logger = logging.getLogger(__name__)



class DmDeal(models.Model):
    """Main Deal Management Model
    
    Sprint 1 Changes:
    - Added ALL milestone three-layer date fields (7 milestones)
    - Added get_milestone_date() method as single source of truth
    - Fixed confirmation_date field
    - Enhanced validation workflow
    
    Allocation System Updates:
    - Updated to use new dm.allocation model with direct relationship
    - Removed old orchestrator pattern (source_model/target_model)
    - Added allocation action methods for wizards
    """
    _name = 'dm.deal'
    _description = 'Deal Management'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'dm.cascade.mixin']
    _order = 'id desc'
    _rec_name = 'name'
    
    # Core Fields
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
    
    # State Management
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validated'),
        ('confirmed', 'Confirmed'),
        ('allocated', 'Allocated'),
        ('ready', 'Ready to Ship'),
        ('shipping', 'Shipping'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', required=True, tracking=True)

    # Validation & Confirmation tracking
    validation_date = fields.Date(
        string='Validation Date',
        readonly=True,
        tracking=True,
        help='Date when deal was validated and SO/PO created'
    )
    
    confirmation_date = fields.Date(
        string='Confirmation Date',
        readonly=True,
        tracking=True,
        help='Date when deal was confirmed (after SO/PO confirmation)'
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
    # COMPLETE MILESTONE MATRIX - ALL THREE-LAYER DATES
    # ============================================================
    
    # Milestone 1: Order Confirmation (single date, acts as all three)
    # This is set when deal moves to confirmed state
    # confirmation_date field above serves this purpose
    
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
    
    # Milestone 3: Ready to Ship (RTS) - ALREADY EXISTS
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
    
    # Milestone 6: ETA (Estimated Time of Arrival) - ALREADY EXISTS
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
    # TEMPLATE FIELDS
    # ============================================================

    wizard_selected_template_id = fields.Many2one(
        'dm.deal.template',
        string='Wizard Selected Template',
        help='Temporary storage for template selected from wizard'
    )
    
    template_id = fields.Many2one(
        'dm.deal.template',
        string='Applied Template',
        readonly=True
    )

    template_selection_pending = fields.Boolean(
        string='Template Selection Pending',
        default=False,
        help='Multiple templates match - user needs to select one'
    )
    
    # ============================================================
    # COMMERCIAL TERMS
    # ============================================================
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True)],
        tracking=True,
        readonly="state not in ['draft']"
    )
    
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
    # ALLOCATION RELATIONSHIPS (NEW PATTERN)
    # ============================================================
    
    # Direct relationship to allocations
    allocation_ids = fields.One2many(
        'dm.allocation',
        'deal_id',
        string='Allocations'
    )
    
    # Computed allocation status
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
    
    # Computed relationships to production runs and shipments
    

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
    # CONTAINER TOTALS - Sprint 4 (Package Configuration Extension)
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
    # MILESTONE GETTER - SINGLE SOURCE OF TRUTH
    # ============================================================
    
    def get_milestone_date(self, milestone_code, prefer='best'):
        """
        Get milestone date with fallback logic.
        CRITICAL: This is the single source of truth for milestone dates.
        Payment terms and all other modules MUST use this method.
        
        Args:
            milestone_code: 'order_conf', 'prod_start', 'rts', 'loading', 
                           'etd', 'eta', 'delivery'
            prefer: 'actual', 'current', 'requested', or 'best' (auto-select best available)
        
        Returns:
            Date or False
        """
        self.ensure_one()
        
        # Milestone mapping: (requested, current, actual)
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
        
        # Return based on preference
        if prefer == 'actual':
            return actual
        elif prefer == 'current':
            return current or requested
        elif prefer == 'requested':
            return requested
        else:  # 'best' - use most recent/accurate
            return actual or current or requested
    
    # ============================================================
    # COMPUTED METHODS - BASIC
    # ============================================================

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
            # If manually requested, don't override
            if deal.production_start_requested:
                deal.production_start_calculated = deal.production_start_requested
                continue
            
            rts_date = deal.rts_current or deal.rts_requested
            
            if rts_date and deal.line_ids:
                # Use maximum cycle time from all products
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
            # Check SO confirmation
            if deal.sale_order_ids:
                deal.so_confirmed = any(
                    so.state in ['sale', 'done'] 
                    for so in deal.sale_order_ids
                )
            else:
                deal.so_confirmed = False
            
            # Check PO confirmation
            if deal.purchase_order_ids:
                deal.po_confirmed = any(
                    po.state in ['purchase', 'done']
                    for po in deal.purchase_order_ids
                )
            else:
                # If no supplier, PO confirmation not required
                deal.po_confirmed = False if deal.supplier_id else True
            
            # Build status display
            so_status = '✓ SO' if deal.so_confirmed else '○ SO'
            po_status = '✓ PO' if deal.po_confirmed else '○ PO'
            deal.confirmation_status_display = f"{so_status} | {po_status}"
    
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
            
            if deal.total_sale_amount > 0:
                deal.margin_percentage = (deal.margin_amount / deal.total_sale_amount) * 100
            else:
                deal.margin_percentage = 0.0
    
    @api.depends('line_ids.containers_required', 'line_ids.container_teu')
    def _compute_container_totals(self):
        """Sum containers and TEU from all deal lines"""
        for deal in self:
            deal.total_containers = sum(deal.line_ids.mapped('containers_required'))
            deal.total_teu = sum(deal.line_ids.mapped('container_teu'))
    
    @api.depends('line_ids.containers_required', 'line_ids.container_type_id', 'total_teu')
    def _compute_container_summary(self):
        """Generate human-readable container summary"""
        for deal in self:
            if not deal.line_ids or not deal.total_containers:
                deal.container_summary = "No containers calculated"
                continue
            
            # Group by container type
            container_types = {}
            for line in deal.line_ids:
                if line.containers_required and line.container_type_id:
                    type_name = line.container_type_id.name or 'Unknown'
                    if type_name not in container_types:
                        container_types[type_name] = 0.0
                    container_types[type_name] += line.containers_required
            
            # Build summary string
            if container_types:
                parts = []
                for type_name, qty in sorted(container_types.items()):
                    parts.append(f"{qty:.1f}× {type_name}")
                summary = " + ".join(parts)
                deal.container_summary = f"{summary} = {deal.total_teu:.1f} TEU"
            else:
                deal.container_summary = f"{deal.total_containers:.1f} containers = {deal.total_teu:.1f} TEU"
    
    def _compute_counts(self):
        """Compute counts for SO/PO"""
        for deal in self:
            deal.so_count = len(deal.sale_order_ids)
            deal.po_count = len(deal.purchase_order_ids)



    @api.depends('allocation_ids', 'allocation_ids.state')
    def _compute_allocation_counts(self):
        """Count active allocations"""
        for deal in self:
            active_allocations = deal.allocation_ids.filtered(
                lambda a: a.state in ['active', 'completed']
            )
            deal.allocation_count = len(active_allocations)
    
    @api.depends('allocation_ids', 'allocation_ids.state', 'allocation_ids.allocation_type')
    def _compute_allocation_status(self):
        """
        Compute allocation status from active AND completed allocations.
        Generic implementation - production/shipment modules can extend.
        
        FIXED: Now includes 'completed' state so status doesn't reset
        when PR/Shipment is marked as done.
        """
        for deal in self:
            # Include BOTH active and completed allocations
            active_allocations = deal.allocation_ids.filtered(
                lambda a: a.state in ['active', 'completed']
            )
            
            if not active_allocations:
                deal.allocation_status = 'unallocated'
            elif len(active_allocations) >= 2:
                # Has at least 2 allocations (production + shipment)
                deal.allocation_status = 'allocated'
            else:
                # Has 1 allocation (either production or shipment)
                deal.allocation_status = 'partial'
    def action_validate(self):
        """
        SPRINT 1: Validate deal and create SO/PO in draft state.
        This is the NEW workflow entry point after draft.
        """
        for deal in self:
            if deal.state != 'draft':
                raise UserError(_('Only draft deals can be validated'))
            
            if not deal.line_ids:
                raise UserError(_('Cannot validate deal without product lines'))
            
            if not deal.customer_id:
                raise UserError(_('Customer is required'))
            
            if not deal.customer_po_number:
                raise UserError(_('Customer PO# is required'))
            
            # Set validation date
            deal.validation_date = fields.Date.today()
            
            # Create SO and PO
            try:
                deal._create_sale_order()
                
                if deal.supplier_id:
                    deal._create_purchase_order()
                else:
                    _logger.info(f"No supplier set for deal {deal.name}, PO will be created later")
                
                # Move to validated state
                deal.state = 'validated'
                
                deal.message_post(
                    body=_('Deal validated. Sales Order and Purchase Order created in draft/RFQ state.'),
                    subtype_xmlid='mail.mt_comment'
                )
                
                _logger.info(f"Deal {deal.name} validated successfully - SO/PO created")
                
            except Exception as e:
                _logger.error(f"Error validating deal {deal.name}: {str(e)}")
                raise UserError(_(f"Failed to validate deal: {str(e)}"))
        
        return True

    def action_confirm(self):
        """
        SPRINT 1: Confirm deal (normally auto-triggered by SO/PO confirmation).
        This creates downpayment requests and other financial documents.
        """
        for deal in self:
            if deal.state != 'validated':
                raise UserError(_('Only validated deals can be confirmed'))
            
            # Set confirmation date (acts as order_conf milestone)
            if not deal.confirmation_date:
                deal.confirmation_date = fields.Date.today()
            
            # Move to confirmed state
            deal.state = 'confirmed'
            
            # Now create downpayment requests (moved here from write())
            if hasattr(deal, '_create_downpayment_requests'):
                try:
                    deal._create_downpayment_requests()
                except Exception as e:
                    _logger.error(f"Error creating downpayments for deal {deal.name}: {str(e)}")
            
            # Create invoice split config if needed
            if deal.invoice_split and hasattr(deal, '_create_invoice_split_config'):
                try:
                    deal._create_invoice_split_config()
                except Exception as e:
                    _logger.error(f"Error creating invoice split config: {str(e)}")
            
            # Generate cash flow projection if method exists
            if hasattr(deal, '_generate_cash_flow_projection'):
                try:
                    deal._create_downpayment_requests()
                except Exception as e:
                    _logger.error(f"Error generating cash flow: {str(e)}")
            
            deal.message_post(
                body=_('Deal confirmed. Downpayment requests and financial documents created.'),
                subtype_xmlid='mail.mt_comment'
            )
            
            _logger.info(f"Deal {deal.name} confirmed successfully")
        
        return True
    
    def _check_auto_confirmation(self):
        """
        SPRINT 1: Auto-confirm deal when both SO and PO are confirmed.
        Called from sale.order.action_confirm() and purchase.order.button_confirm()
        """
        for deal in self:
            if deal.state != 'validated':
                continue
            
            # Skip if already in confirmation process
            if self._context.get('skip_auto_confirm_check'):
                continue
            
            # Check if SO and PO are both confirmed
            if deal.so_confirmed and deal.po_confirmed:
                _logger.info(f"Auto-confirming deal {deal.name} - both SO and PO are confirmed")
                
                try:
                    deal.with_context(skip_auto_confirm_check=True).action_confirm()
                except Exception as e:
                    _logger.error(f"Error in auto-confirmation of deal {deal.name}: {str(e)}")
                    # Post message but don't block SO/PO confirmation
                    deal.message_post(
                        body=f"Automatic deal confirmation failed: {str(e)}. Please confirm manually.",
                        subtype_xmlid='mail.mt_warning'
                    )
    
    # ============================================================
    # SO/PO CREATION
    # ============================================================
    
    def _create_sale_order(self):
        """
        SPRINT v2-2: Create Sales Order with CORRECT field mapping.
        
        FIXES:
        - Currency: Uses deal.currency_id (not customer default)
        - Quantities: Uses package quantities (not unit quantities)
        - UoM: Uses packaging_uom_id (auto-created package UoM)
        - Prices: Maintains 6-decimal precision from deal lines
        - Incoterm location: Uses discharge_port_id.name
        - Commitment date: Uses ETA (current or requested)
        """
        self.ensure_one()
        
        if not self.customer_id:
            raise UserError(_('Customer is required to create Sales Order'))
        
        if not self.line_ids:
            raise UserError(_('Cannot create SO without deal lines'))
        
        SaleOrder = self.env['sale.order']
        
        # FIX 1: Get or create pricelist matching deal currency
        pricelist = self._get_customer_pricelist()
        
        # Prepare SO values with CORRECTED mappings
        so_vals = {
            'partner_id': self.customer_id.id,
            'client_order_ref': self.customer_po_number,
            'date_order': fields.Datetime.now(),
            
            # FIX 2: Use deal currency explicitly
            'currency_id': self.currency_id.id,
            
            # Pricelist matching deal currency
            'pricelist_id': pricelist.id,
            
            # Payment terms
            'payment_term_id': self.sale_payment_term_id.id if self.sale_payment_term_id else False,
            
            # FIX 3: Incoterms with proper location
            'incoterm': self.sale_incoterm_id.id if self.sale_incoterm_id else False,
            'incoterm_location': self.discharge_port_id.name if self.discharge_port_id else self.sale_incoterm_location or '',
            
            # FIX 4: Commitment date = ETA (customer arrival expectation)
            'commitment_date': self.eta_current or self.eta_requested or False,
            
            # Deal reference
            'dm_deal_id': self.id,
            
            # Notes
            'note': (
                f"Deal: {self.name}\n"
                f"Customer PO: {self.customer_po_number}\n"
                f"Ports: {self.loading_port_id.name if self.loading_port_id else 'TBD'} → "
                f"{self.discharge_port_id.name if self.discharge_port_id else 'TBD'}"
            ),
            
            # Order lines
            'order_line': []
        }
        
        # Create SO lines from deal lines with CORRECTED quantities
        for line in self.line_ids:
            if not line.product_id or not line.product_packaging_id:
                _logger.warning(f"Skipping deal line without product/packaging: {line.id}")
                continue
            
            # FIX 5: Ensure packaging UoM exists
            if not line.packaging_uom_id:
                raise UserError(
                    f"Package UoM not found for product '{line.product_id.name}' "
                    f"with packaging '{line.product_packaging_id.name}'. "
                    f"Please check packaging configuration."
                )
            
            so_line_vals = {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                
                # FIX 6: CRITICAL - Use package quantities (NOT unit quantities)
                'product_uom_qty': line.quantity_packaging,  # This is the PRIMARY quantity
                'product_uom': line.packaging_uom_id.id,  # Package UoM (e.g., "Case (Product Name)")
                'product_packaging_id': line.product_packaging_id.id,  # Reference to packaging record
                
                # FIX 7: CRITICAL - Use package price with 6-decimal precision
                'price_unit': line.price_packaging_sale,  # This is already in deal currency
                
                # No discount by default
                'discount': 0.0,
                
                # Taxes from product
                'tax_id': [(6, 0, line.product_id.taxes_id.ids)],
                
                # Customer lead time
                'customer_lead': 0,  # No additional lead time beyond commitment_date
                
                # Link back to deal line for traceability
                'dm_deal_line_id': line.id,
            }
            
            so_vals['order_line'].append((0, 0, so_line_vals))
        
        # Validation before creation
        if not so_vals['order_line']:
            raise UserError(_('No valid lines to create Sales Order'))
        
        # Create the SO
        try:
            so = SaleOrder.create(so_vals)
            
            # Link SO back to deal
            self.sale_order_ids = [(4, so.id)]
            
            # Link SO lines back to deal lines (for quantity tracking)
            for so_line in so.order_line:
                if so_line.dm_deal_line_id:
                    so_line.dm_deal_line_id.sale_order_line_id = so_line.id
            
            _logger.info(
                f"✓ Created SO {so.name} for deal {self.name}:\n"
                f"  - Currency: {self.currency_id.name}\n"
                f"  - Lines: {len(so.order_line)}\n"
                f"  - Total: {so.amount_total:.2f} {so.currency_id.name}\n"
                f"  - Incoterm: {so.incoterm.code if so.incoterm else 'N/A'} {so.incoterm_location or ''}\n"
                f"  - ETA: {so.commitment_date or 'Not set'}"
            )
            
            return so
            
        except Exception as e:
            _logger.error(f"✗ Failed to create SO for deal {self.name}: {str(e)}")
            raise UserError(_(f"Failed to create Sales Order: {str(e)}"))

    def _get_customer_pricelist(self):
        """Get pricelist matching deal currency"""
        self.ensure_one()
        
        # Search for pricelist with our naming convention
        pricelist_name = f"{self.customer_id.name} Pricelist ({self.currency_id.name})"
        
        pricelist = self.env['product.pricelist'].search([
            ('name', '=', pricelist_name),
            ('currency_id', '=', self.currency_id.id),
            ('company_id', 'in', [self.company_id.id, False]),
            ('active', '=', True)
        ], limit=1)
        
        if pricelist:
            _logger.info(
                f"✓ Found pricelist '{pricelist.name}' for {self.customer_id.name} "
                f"in {self.currency_id.name}"
            )
            return pricelist
        
        # Fallback: use customer's default
        pricelist = self.customer_id.property_product_pricelist
        
        if pricelist.currency_id != self.currency_id:
            _logger.warning(
                f"⚠ No pricelist found in {self.currency_id.name} for {self.customer_id.name}. "
                f"Using default pricelist ({pricelist.currency_id.name}). Currency mismatch!"
            )
        
        return pricelist
    
    def _create_purchase_order(self):
        """
        SPRINT v2-2: Create Purchase Order with CORRECT field mapping.
        
        FIXES:
        - Currency: Uses deal.currency_id (not supplier default)
        - Quantities: Uses package quantities (not unit quantities)
        - UoM: Uses packaging_uom_id (auto-created package UoM)
        - Prices: Maintains 6-decimal precision from deal lines
        - Incoterm location: Uses loading_port_id.name
        - Expected date: Uses production_start_calculated
        """
        self.ensure_one()
        
        if not self.supplier_id:
            _logger.info(f"No supplier set for deal {self.name}, skipping PO creation")
            return False
        
        if not self.line_ids:
            raise UserError(_('Cannot create PO without deal lines'))
        
        PurchaseOrder = self.env['purchase.order']
        
        # Prepare PO values with CORRECTED mappings
        po_vals = {
            'partner_id': self.supplier_id.id,
            'partner_ref': self.customer_po_number,  # Our PO# becomes their reference
            'date_order': fields.Datetime.now(),
            
            # FIX 1: Use deal currency explicitly
            'currency_id': self.currency_id.id,
            
            # Payment terms
            'payment_term_id': self.purchase_payment_term_id.id if self.purchase_payment_term_id else False,
            
            # FIX 2: Incoterms with proper location
            'incoterm_id': self.purchase_incoterm_id.id if self.purchase_incoterm_id else False,
            'incoterm_location': self.loading_port_id.name if self.loading_port_id else self.purchase_incoterm_location or '',
            
            # FIX 3: Expected date = production_start_calculated (or fallback to RTS)
            'date_planned': self.production_start_calculated or self.rts_current or self.rts_requested or fields.Date.today(),
            
            # Deal reference
            'dm_deal_id': self.id,
            
            # Notes
            'notes': (
                f"Deal: {self.name}\n"
                f"Customer PO: {self.customer_po_number}\n"
                f"Production Start: {self.production_start_calculated or 'TBD'}\n"
                f"RTS Target: {self.rts_current or self.rts_requested or 'TBD'}\n"
                f"Loading Port: {self.loading_port_id.name if self.loading_port_id else 'TBD'}"
            ),
            
            # Order lines
            'order_line': []
        }
        
        # Create PO lines from deal lines with CORRECTED quantities
        for line in self.line_ids:
            if not line.product_id or not line.product_packaging_id:
                _logger.warning(f"Skipping deal line without product/packaging: {line.id}")
                continue
            
            # FIX 4: Ensure packaging UoM exists
            if not line.packaging_uom_id:
                raise UserError(
                    f"Package UoM not found for product '{line.product_id.name}' "
                    f"with packaging '{line.product_packaging_id.name}'. "
                    f"Please check packaging configuration."
                )
            
            po_line_vals = {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                
                # FIX 5: CRITICAL - Use package quantities (NOT unit quantities)
                'product_qty': line.quantity_packaging,  # This is the PRIMARY quantity
                'product_uom': line.packaging_uom_id.id,  # Package UoM
                'product_packaging_id': line.product_packaging_id.id,  # Reference to packaging
                
                # FIX 6: CRITICAL - Use package price with 6-decimal precision
                'price_unit': line.price_packaging_purchase,  # Already in deal currency
                
                # Delivery date (same as PO header for simplicity)
                'date_planned': po_vals['date_planned'],
                
                # Taxes from product
                'taxes_id': [(6, 0, line.product_id.supplier_taxes_id.ids)],
                
                # Link back to deal line for traceability
                'dm_deal_line_id': line.id,
            }
            
            po_vals['order_line'].append((0, 0, po_line_vals))
        
        # Validation before creation
        if not po_vals['order_line']:
            raise UserError(_('No valid lines to create Purchase Order'))
        
        # Create the PO
        try:
            po = PurchaseOrder.create(po_vals)
            
            # Link PO back to deal
            self.purchase_order_ids = [(4, po.id)]
            
            # Link PO lines back to deal lines (for quantity tracking)
            for po_line in po.order_line:
                if po_line.dm_deal_line_id:
                    po_line.dm_deal_line_id.purchase_order_line_id = po_line.id
            
            _logger.info(
                f"✓ Created PO {po.name} for deal {self.name}:\n"
                f"  - Currency: {self.currency_id.name}\n"
                f"  - Lines: {len(po.order_line)}\n"
                f"  - Total: {po.amount_total:.2f} {po.currency_id.name}\n"
                f"  - Incoterm: {po.incoterm_id.code if po.incoterm_id else 'N/A'} {po.incoterm_location or ''}\n"
                f"  - Expected: {po.date_planned}"
            )
            
            return po
            
        except Exception as e:
            _logger.error(f"✗ Failed to create PO for deal {self.name}: {str(e)}")
            raise UserError(_(f"Failed to create Purchase Order: {str(e)}"))

    # ============================================================
    # TEMPLATE METHODS (UNCHANGED)
    # ============================================================
    
    @api.model
    def create(self, vals):
        if vals.get('name', 'New') == 'New':
            vals['name'] = self.env['ir.sequence'].next_by_code('dm.deal') or 'New'
        
        deal = super().create(vals)
        
        if deal.line_ids and not deal.template_id:
            deal._apply_template_from_lines()
        
        return deal
    
    @api.onchange('line_ids')
    def _onchange_apply_template(self):
        """
        Enhanced onchange with template validation for subsequent lines.
        """
        if not self.line_ids or self._context.get('no_template'):
            return
        
        # Skip if we're already in template selection process
        if self.template_selection_pending:
            return
        
        # If template already applied, validate new line compatibility
        if self.template_id:
            return self._validate_new_line_template()
        
        # No template yet - try to apply
        return self._apply_template_from_lines()

    def _validate_new_line_template(self):
        """
        Validate that newly added line's product matches current deal template.
        Called when deal already has a template applied.
        """
        self.ensure_one()
        
        if not self.line_ids or not self.template_id:
            return
        
        # Get the last (most recently added) line
        new_line = self.line_ids[-1]
        product = new_line.product_id
        
        if not product:
            return
        
        # Find best template for this product
        product_templates = self.env['dm.deal.template'].find_best_template(
            product_id=product.id,
            category_id=product.categ_id.id,
            customer_id=self.customer_id.id,
            supplier_id=self.supplier_id.id if self.supplier_id else None,
            return_all=True
        )
        
        # Check if current deal template is in the list
        if self.template_id not in product_templates:
            return {
                'warning': {
                    'title': _('Template Mismatch'),
                    'message': _(
                        f"Product '{product.name}' does not match the current deal template '{self.template_id.name}'.\n\n"
                        f"This may result in incorrect commercial terms or pricing.\n\n"
                        f"Consider:\n"
                        f"• Removing this product and creating a separate deal\n"
                        f"• Manually adjusting commercial terms for this line"
                    )
                }
            }
    
    def _apply_template_from_lines(self):
        """Apply template using FIRST LINE's supplier"""
        _logger.warning("🎯 _apply_template_from_lines CALLED")
        
        if not self.line_ids:
            _logger.warning("   ❌ No lines")
            return
        
        first_line = self.line_ids[0]
        product = first_line.product_id
        
        if not product:
            _logger.warning("   ❌ No product on first line")
            return
        
        # CRITICAL: Use LINE's supplier, not deal's!
        line_supplier = first_line.supplier_id
        supplier_filter = line_supplier.id if line_supplier else None
        
        _logger.warning(f"   🔍 Template search:")
        _logger.warning(f"      - Product: {product.name}")
        _logger.warning(f"      - Customer: {self.customer_id.name if self.customer_id else 'None'}")
        _logger.warning(f"      - Supplier (from LINE): {line_supplier.name if line_supplier else 'None'}")
        
        # Find matching templates
        matching_templates = self.env['dm.deal.template'].find_best_template(
            product_id=product.id,
            category_id=product.categ_id.id,
            customer_id=self.customer_id.id,
            supplier_id=supplier_filter,
            return_all=True
        )
        
        template_count = len(matching_templates)
        _logger.warning(f"   ✅ Found {template_count} templates")
        
        for tmpl in matching_templates:
            _logger.warning(f"      - {tmpl.name} (supplier: {tmpl.supplier_id.name if tmpl.supplier_id else 'Any'})")
        
        if template_count == 0:
            return {
                'warning': {
                    'title': _('No Template Found'),
                    'message': _(f"No template found for:\n"
                               f"• Customer: {self.customer_id.name}\n"
                               f"• Supplier: {line_supplier.name if line_supplier else 'Any'}\n"
                               f"• Product: {product.name}")
                }
            }
        
        elif template_count == 1:
            template = matching_templates[0]
            _logger.warning(f"   ✅ Single template - auto-applying: {template.name}")
            self._apply_single_template(template)
            
            return {
                'warning': {
                    'title': _('Template Applied'),
                    'message': _(f"Template '{template.name}' applied.")
                }
            }
        
        else:
            _logger.warning(f"   📋 Multiple templates - opening wizard")
            self.template_selection_pending = True
            return self._open_template_selection_wizard(matching_templates)

    def _apply_single_template(self, template):
        """Apply template and sync supplier to deal header"""
        _logger.warning("🎯 _apply_single_template CALLED")
        _logger.warning(f"   Template: {template.name}")
        
        self.ensure_one()
        
        # Apply commercial terms
        self.apply_template(template)
        
        # Set template_id
        self.template_id = template
        _logger.warning(f"   ✅ Template ID set")
        
        # CRITICAL: Copy supplier from first line to deal header
        if self.line_ids and self.line_ids[0].supplier_id:
            line_supplier = self.line_ids[0].supplier_id
            if not self.supplier_id:
                self.supplier_id = line_supplier
                _logger.warning(f"   ✅ Copied supplier from line to deal: {line_supplier.name}")
            elif self.supplier_id != line_supplier:
                _logger.warning(f"   ⚠️ WARNING: Deal supplier mismatch!")
        
        # Alternative: Use template supplier if available
        elif template.supplier_id and not self.supplier_id:
            self.supplier_id = template.supplier_id
            _logger.warning(f"   ✅ Set supplier from template: {template.supplier_id.name}")
        
        self.template_selection_pending = False
        
        _logger.warning(f"   Final: template={self.template_id.name}, supplier={self.supplier_id.name if self.supplier_id else 'NOT SET'}")

    def _open_template_selection_wizard(self, templates):
        """Open wizard - WITH DIAGNOSTIC LOGGING"""
        _logger.warning("📷 DIAGNOSTIC: _open_template_selection_wizard CALLED")
        _logger.warning(f"   Templates to show: {len(templates)}")
        for tmpl in templates:
            _logger.warning(f"      - {tmpl.name}")
        
        wizard_vals = {
            'template_ids': [(6, 0, templates.ids)],
        }
        
        # Only set deal_id if deal is saved
        if self.id and not isinstance(self.id, models.NewId):
            wizard_vals['deal_id'] = self.id
            _logger.warning(f"   Deal ID added to wizard: {self.id}")
        else:
            _logger.warning(f"   Deal not saved yet - no deal_id in wizard")
        
        wizard = self.env['dm.deal.template.selection.wizard'].create(wizard_vals)
        _logger.warning(f"   Wizard created: ID={wizard.id}")
        
        return {
            'name': _('Select Deal Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.template.selection.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def apply_selected_template_from_wizard(self, template_id):
        """
        Apply template selected from wizard.
        Called after wizard closes with selected template.
        """
        self.ensure_one()
        
        template = self.env['dm.deal.template'].browse(template_id)
        if template.exists():
            self.apply_template(template)
            self.template_selection_pending = False
            
            self.message_post(
                body=_(f"Template '{template.name}' applied via selection wizard"),
                subtype_xmlid='mail.mt_note'
            )
    
    def apply_template(self, template):
        """Apply template settings to deal - with field validation"""
        self.ensure_one()
        
        if not template:
            return
        
        values = {}
        
        # Get valid field names for dm.deal model
        valid_fields = set(self._fields.keys())
        
        # Template fields to apply (with fallbacks)
        template_field_mapping = {
            # Sales terms
            'sale_payment_term_id': template.sale_payment_term_id.id if template.sale_payment_term_id else False,
            'sale_incoterm_id': template.sale_incoterm_id.id if template.sale_incoterm_id else False,
            'sale_incoterm_location': template.sale_incoterm_location or False,
            
            # Purchase terms
            'purchase_payment_term_id': template.purchase_payment_term_id.id if template.purchase_payment_term_id else False,
            'purchase_incoterm_id': template.purchase_incoterm_id.id if template.purchase_incoterm_id else False,
            'purchase_incoterm_location': template.purchase_incoterm_location or False,
            
            # Ports
            'loading_port_id': template.loading_port_id.id if template.loading_port_id else False,
            'discharge_port_id': template.discharge_port_id.id if template.discharge_port_id else False,
            
            # Invoice split
            'invoice_split': template.invoice_split if hasattr(template, 'invoice_split') else False,
            'product_invoice_percentage': template.product_invoice_percentage if hasattr(template, 'product_invoice_percentage') else 0,
        }
        
        # Only add fields that exist in the model
        for field_name, field_value in template_field_mapping.items():
            if field_name in valid_fields and field_value:
                values[field_name] = field_value
        
        # Apply values if any
        if values:
            self.write(values)
            _logger.info(f"Applied template {template.name} to deal {self.name}")
        
        return True
    
    def action_cancel(self):
        for deal in self:
            if deal.state in ['delivered', 'paid']:
                raise UserError(f"Cannot cancel deal in state '{deal.state}'.")
            
            if hasattr(self.env['dm.cancellation.handler'], 'handle_deal_cancellation'):
                self.env['dm.cancellation.handler'].handle_deal_cancellation(deal)
            
            for so in deal.sale_order_ids.filtered(lambda o: o.state in ['draft', 'sent']):
                so.action_cancel()
            
            for po in deal.purchase_order_ids.filtered(lambda o: o.state in ['draft', 'sent']):
                po.button_cancel()
            
            deal.state = 'cancelled'
            
            deal.message_post(
                body=f"Deal cancelled by {self.env.user.name}",
                subtype_xmlid='mail.mt_comment'
            )
        
        return True

    # ============================================================
    # VIEW ACTION METHODS
    # ============================================================

    def action_view_sale_orders(self):
        """Open related sales orders"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('sale.action_orders')
        action['domain'] = [('dm_deal_id', '=', self.id)]
        action['context'] = {'default_dm_deal_id': self.id}
        if len(self.sale_order_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.sale_order_ids.id
        return action

    def action_view_purchase_orders(self):
        """Open related purchase orders"""
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id('purchase.purchase_form_action')
        action['domain'] = [('dm_deal_id', '=', self.id)]
        action['context'] = {'default_dm_deal_id': self.id}
        if len(self.purchase_order_ids) == 1:
            action['views'] = [(False, 'form')]
            action['res_id'] = self.purchase_order_ids.id
        return action




    def action_view_allocations(self):
        """Open allocation records"""
        self.ensure_one()
        return {
            'name': _('Deal Allocations'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.allocation',
            'view_mode': 'tree,form',
            'domain': [('deal_id', '=', self.id)],
            'context': {'default_deal_id': self.id},
        }



    def action_deallocate_all(self):
        """Cancel all active allocations"""
        self.ensure_one()
        active_allocations = self.allocation_ids.filtered(lambda a: a.state == 'active')
        if active_allocations:
            active_allocations.action_cancel()
            self.message_post(body=_("All allocations cancelled"))
            # Reset state to confirmed
            if self.state in ['allocated', 'partial', 'ready']:
                self.state = 'confirmed'
        return True

    def action_select_template(self):
        """
        Manual action to open template selection wizard.
        Used when template_selection_pending = True.
        """
        self.ensure_one()
        
        # Find matching templates
        if self.line_ids:
            first_product = self.line_ids[0].product_id
            if first_product:
                matching_templates = self.env['dm.deal.template'].find_best_template(
                    product_id=first_product.id,
                    category_id=first_product.categ_id.id,
                    customer_id=self.customer_id.id,
                    supplier_id=self.supplier_id.id if self.supplier_id else None,
                    return_all=True
                )
                
                if matching_templates:
                    return self._open_template_selection_wizard(matching_templates)
        
        raise UserError(_('No matching templates found for this deal.'))
    
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
    
    # ============================================================
    # WRITE METHOD
    # ============================================================
    
    def write(self, vals):
        # DATE CASCADE logging (if needed)
        for deal in self:
            if 'rts_current' in vals and vals['rts_current'] != deal.rts_current:
                if hasattr(deal, 'cascade_date_change'):
                    deal.cascade_date_change('rts_current', deal.rts_current, vals['rts_current'])
        
        res = super().write(vals)
        
        # STATE-BASED updates
        if 'state' in vals:
            for deal in self:
                if vals['state'] == 'ready':
                    # Complete production allocations when deal is ready
                    prod_allocations = deal.allocation_ids.filtered(
                        lambda a: a.allocation_type == 'production' and a.state == 'active'
                    )
                    if prod_allocations:
                        prod_allocations.action_complete()
        
        # AUTO-CONFIRMATION check (if not already in confirmation process)
        if not vals.get('state') and not self._context.get('skip_auto_confirm_check'):
            self._check_auto_confirmation()
        
        return res