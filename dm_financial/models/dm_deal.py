from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDeal(models.Model):
    """Extend deal with financial management features and milestone tracking
    
    REFACTORED for dm_deal v2.4.1+ (orchestrator-based architecture)
    - Uses allocation_ids instead of direct production_run_ids/shipment_ids
    - State-based DP creation (not action override)
    - Orchestrator-aware milestone date computation
    - Module independence with graceful degradation
    """
    _inherit = 'dm.deal'
    
    # ============================================================
    # MILESTONE DATE FIELDS (for downpayment calculations)
    # ============================================================
    
    confirmation_date = fields.Date(
        string='Confirmation Date',
        readonly=True,
        tracking=True,
        help='Date when deal was confirmed (SO and PO confirmed)'
    )
    
    production_start_current = fields.Date(
        string='Production Start Date',
        compute='_compute_production_dates',
        store=True,
        help='Current production start date from production runs (via allocations)'
    )
    
    loading_date_current = fields.Date(
        string='Loading Date',
        compute='_compute_shipment_dates',
        store=True,
        help='Current loading date from shipments (via allocations)'
    )
    
    etd_current = fields.Date(
        string='ETD Current',
        compute='_compute_shipment_dates',
        store=True,
        help='Current ETD from shipments (via allocations)'
    )
    
    delivery_date = fields.Date(
        string='Delivery Date',
        compute='_compute_shipment_dates',
        store=True,
        help='Actual or expected delivery date'
    )
    
    # ============================================================
    # FINANCIAL TRACKING FIELDS
    # ============================================================
    
    downpayment_request_ids = fields.One2many(
        'dm.downpayment.request',
        'deal_id',
        string='Downpayment Requests'
    )
    
    downpayment_count = fields.Integer(
        string='Downpayments',
        compute='_compute_financial_counts'
    )
    
    invoice_split_config_id = fields.Many2one(
        'dm.invoice.split.config',
        string='Invoice Split Config',
        readonly=True
    )
    
    invoice_ids = fields.One2many(
        'account.move',
        'dm_deal_id',
        string='Invoices',
        domain=[('move_type', 'in', ['out_invoice', 'in_invoice'])]
    )
    
    invoice_count = fields.Integer(
        string='Invoices',
        compute='_compute_financial_counts'
    )
    
    # Cash flow fields
    cash_flow_projection = fields.One2many(
        'dm.cash_flow',
        'deal_id',
        string='Cash Flow Projection'
    )
    
    total_receivable = fields.Monetary(
        string='Total Receivable',
        compute='_compute_financial_summary',
        currency_field='currency_id'
    )
    
    total_payable = fields.Monetary(
        string='Total Payable',
        compute='_compute_financial_summary',
        currency_field='currency_id'
    )
    
    gross_margin = fields.Monetary(
        string='Gross Margin',
        compute='_compute_financial_summary',
        currency_field='currency_id'
    )
    
    gross_margin_percent = fields.Float(
        string='Gross Margin %',
        compute='_compute_financial_summary'
    )
    
    # Payment milestone dates (for reference)
    payment_milestone_dates = fields.Text(
        string='Payment Milestones',
        compute='_compute_payment_milestones'
    )
    
    # Computed totals for compatibility
    total_value = fields.Monetary(
        string='Total Sales Value',
        compute='_compute_deal_totals',
        store=True,
        currency_field='currency_id'
    )
    
    purchase_total = fields.Monetary(
        string='Total Purchase Value',
        compute='_compute_deal_totals',
        store=True,
        currency_field='currency_id'
    )
    
    # ============================================================
    # COMPUTE METHODS FOR MILESTONE DATES (ORCHESTRATOR-AWARE)
    # ============================================================
    
    @api.depends('allocation_ids', 'allocation_ids.state', 
                 'allocation_ids.allocation_type', 'allocation_ids.production_run_id',
                 'rts_current', 'rts_requested', 'confirmation_date')
    def _compute_production_dates(self):
        """Get production dates via orchestrator allocations OR estimate from RTS
        
        REFACTORED: Uses allocation_ids instead of direct production_run_ids access
        """
        for deal in self:
            # Check if dm_production module is installed
            dm_production_installed = self._check_module_installed('dm_production')
            
            if dm_production_installed and hasattr(deal, 'allocation_ids'):
                # Get production runs via allocations (orchestrator pattern)
                pr_allocations = deal.allocation_ids.filtered(
                    lambda a: a.allocation_type == 'deal_to_production'
                    and a.state in ['active', 'completed']
                    and hasattr(a, 'production_run_id')
                    and a.production_run_id
                )
                
                if pr_allocations:
                    production_runs = pr_allocations.mapped('production_run_id')
                    active_runs = production_runs.filtered(
                        lambda pr: pr.state not in ['cancelled', 'draft']
                    )
                    
                    if active_runs:
                        # Extract dates from production runs
                        start_dates = []
                        for run in active_runs:
                            if hasattr(run, 'production_start_date') and run.production_start_date:
                                start_dates.append(run.production_start_date)
                            elif hasattr(run, 'start_date') and run.start_date:
                                start_dates.append(run.start_date)
                            elif hasattr(run, 'rts_target') and run.rts_target:
                                # Estimate from PR's RTS target
                                approx_start = run.rts_target - timedelta(days=14)
                                start_dates.append(approx_start)
                        
                        deal.production_start_current = min(start_dates) if start_dates else False
                        if deal.production_start_current:
                            _logger.info(
                                f"Production start for {deal.name}: {deal.production_start_current} "
                                f"(from {len(active_runs)} production run(s))"
                            )
                            continue
            
            # FALLBACK: Estimate from RTS date (works with or without dm_production)
            rts_date = deal.rts_actual or deal.rts_current or deal.rts_requested
            if rts_date:
                deal.production_start_current = rts_date - timedelta(days=14)
                _logger.debug(
                    f"Estimated production start for {deal.name}: {deal.production_start_current} "
                    f"(14 days before RTS {rts_date})"
                )
            elif deal.confirmation_date:
                # Final fallback: confirmation date + 7 days
                deal.production_start_current = deal.confirmation_date + timedelta(days=7)
                _logger.debug(
                    f"Fallback production start for {deal.name}: {deal.production_start_current} "
                    f"(7 days after confirmation)"
                )
            else:
                deal.production_start_current = False
    
    @api.depends('allocation_ids', 'allocation_ids.state',
                 'allocation_ids.allocation_type', 'allocation_ids.shipment_id')
    def _compute_shipment_dates(self):
        """Get shipment dates via orchestrator allocations
        
        REFACTORED: Uses allocation_ids instead of direct shipment_ids access
        """
        for deal in self:
            # Check if dm_shipment module is installed
            dm_shipment_installed = self._check_module_installed('dm_shipment')
            
            if dm_shipment_installed and hasattr(deal, 'allocation_ids'):
                # Get shipments via allocations (orchestrator pattern)
                ship_allocations = deal.allocation_ids.filtered(
                    lambda a: a.allocation_type == 'deal_to_shipment'
                    and a.state in ['active', 'completed']
                    and hasattr(a, 'shipment_id')
                    and a.shipment_id
                )
                
                if ship_allocations:
                    shipments = ship_allocations.mapped('shipment_id')
                    active_shipments = shipments.filtered(
                        lambda s: s.state not in ['cancelled', 'draft']
                    )
                    
                    if active_shipments:
                        # Get dates from first/primary shipment
                        ship = active_shipments[0]
                        
                        # Try different field names for loading date
                        if hasattr(ship, 'loading_date'):
                            deal.loading_date_current = ship.loading_date
                        elif hasattr(ship, 'loading_date_actual'):
                            deal.loading_date_current = ship.loading_date_actual
                        else:
                            deal.loading_date_current = False
                        
                        # ETD
                        if hasattr(ship, 'etd'):
                            deal.etd_current = ship.etd
                        elif hasattr(ship, 'etd_current'):
                            deal.etd_current = ship.etd_current
                        else:
                            deal.etd_current = False
                        
                        # Delivery date (use ETA as proxy)
                        if hasattr(ship, 'eta_actual'):
                            deal.delivery_date = ship.eta_actual
                        elif hasattr(ship, 'eta_current'):
                            deal.delivery_date = ship.eta_current
                        elif hasattr(ship, 'eta'):
                            deal.delivery_date = ship.eta
                        else:
                            deal.delivery_date = False
                        
                        continue
            
            # No shipments or module not installed
            deal.loading_date_current = False
            deal.etd_current = False
            deal.delivery_date = False
    
    # ============================================================
    # STATE CHANGE HOOKS (REFACTORED)
    # ============================================================
    
    def write(self, vals):
        """
        Override to capture confirmation date and handle financial document creation.
        
        CRITICAL: Uses context flag to prevent duplicate DP creation during
        multiple write() calls in the same transaction.
        """
        
        # Capture confirmation date when state changes to confirmed
        if vals.get('state') == 'confirmed':
            for deal in self:
                if not deal.confirmation_date:
                    vals['confirmation_date'] = fields.Date.today()
        
        res = super().write(vals)
        
        # CRITICAL: Create downpayments ONLY when state changes to confirmed
        # AND only if they don't already exist
        # AND only if we're not already in a DP creation process
        if vals.get('state') == 'confirmed' and not self.env.context.get('creating_downpayments'):
            for deal in self:
                # Check if downpayments already exist for this deal
                existing_dps = self.env['dm.downpayment.request'].search_count([
                    ('deal_id', '=', deal.id)
                ])
                
                if existing_dps == 0:
                    _logger.info(f"Creating downpayment requests for confirmed deal {deal.name}")
                    
                    # Set context flag to prevent re-entry
                    deal.with_context(creating_downpayments=True)._create_downpayment_requests()
                    
                    # Create invoice split config if needed
                    if deal.invoice_split:
                        deal.with_context(creating_downpayments=True)._create_invoice_split_config()
                    
                    # Generate cash flow projection
                    if hasattr(deal, '_generate_cash_flow_projection'):
                        deal.with_context(creating_downpayments=True)._generate_cash_flow_projection()
                else:
                    _logger.info(
                        f"Downpayments already exist for deal {deal.name} "
                        f"({existing_dps} found) - skipping creation"
                    )
        
        # Check if we should auto-confirm based on SO/PO states
        # Only check if state wasn't explicitly set in this write
        # AND if we're not already in a confirmation process
        if not vals.get('state') and not self.env.context.get('skip_auto_confirm_check'):
            self.with_context(skip_auto_confirm_check=True)._check_auto_confirmation()
        
        return res
    
    def _on_deal_confirmed(self):
        """Hook called when deal transitions to confirmed state
        
        REFACTORED: Centralized financial document creation
        Replaces the old action_confirm() override pattern
        """
        self.ensure_one()
        
        _logger.info(f"Deal {self.name} confirmed - triggering financial operations")
        
        # 1. Create downpayment requests (if not already exist)
        existing_dps = self.env['dm.downpayment.request'].search_count([
            ('deal_id', '=', self.id)
        ])
        
        if existing_dps == 0:
            _logger.info(f"  Creating downpayment requests for {self.name}")
            self._create_downpayment_requests()
        else:
            _logger.info(
                f"  Downpayments already exist for {self.name} ({existing_dps} records) - skipping"
            )
        
        # 2. Create invoice split configuration if needed
        if self.invoice_split and not self.invoice_split_config_id:
            _logger.info(f"  Creating invoice split config for {self.name}")
            self._create_invoice_split_config()
        
        # 3. Generate initial cash flow projection
        _logger.info(f"  Generating cash flow projection for {self.name}")
        self._generate_cash_flow_projection()
        
        _logger.info(f"Financial operations completed for {self.name}")
    
    # ============================================================
    # COMPUTE METHODS FOR FINANCIAL FIELDS
    # ============================================================
    
    @api.depends('line_ids.amount_sale', 'line_ids.amount_purchase')
    def _compute_deal_totals(self):
        """Compute deal totals if not already computed in base module"""
        for deal in self:
            # Use existing fields if available, otherwise compute
            if hasattr(deal, 'total_sale_amount'):
                deal.total_value = deal.total_sale_amount
            else:
                deal.total_value = sum(deal.line_ids.mapped('amount_sale')) if deal.line_ids else 0.0
            
            if hasattr(deal, 'total_purchase_amount'):
                deal.purchase_total = deal.total_purchase_amount
            else:
                deal.purchase_total = sum(deal.line_ids.mapped('amount_purchase')) if deal.line_ids else 0.0
    
    @api.depends('downpayment_request_ids', 'downpayment_request_ids.state', 'invoice_ids')
    def _compute_financial_counts(self):
        """Compute financial document counts - only active documents"""
        for deal in self:
            # Count only active downpayments (not cancelled)
            active_dps = deal.downpayment_request_ids.filtered(
                lambda dp: dp.state != 'cancelled'
            )
            deal.downpayment_count = len(active_dps)
            
            # Count only posted/draft invoices (not cancelled)
            active_invoices = deal.invoice_ids.filtered(
                lambda inv: inv.state != 'cancel'
            )
            deal.invoice_count = len(active_invoices)
    
    @api.depends('invoice_ids', 'downpayment_request_ids')
    def _compute_financial_summary(self):
        """Compute financial summary for the deal"""
        for deal in self:
            # Receivables
            customer_invoices = deal.invoice_ids.filtered(
                lambda i: i.move_type == 'out_invoice' and i.state == 'posted'
            )
            deal.total_receivable = sum(customer_invoices.mapped('amount_residual'))
            
            # Payables
            supplier_invoices = deal.invoice_ids.filtered(
                lambda i: i.move_type == 'in_invoice' and i.state == 'posted'
            )
            deal.total_payable = sum(supplier_invoices.mapped('amount_residual'))
            
            # Margin calculation
            revenue = sum(customer_invoices.mapped('amount_total'))
            costs = sum(supplier_invoices.mapped('amount_total'))
            
            # Add freight and insurance if CIF
            if deal.sale_incoterm_id and deal.sale_incoterm_id.code in ['CIF', 'CFR']:
                if deal.invoice_split_config_id:
                    costs += deal.invoice_split_config_id.freight_amount
                    if deal.sale_incoterm_id.code == 'CIF':
                        costs += deal.invoice_split_config_id.insurance_amount
            
            deal.gross_margin = revenue - costs
            deal.gross_margin_percent = (deal.gross_margin / revenue * 100) if revenue else 0.0
    
    @api.depends('sale_payment_term_id', 'purchase_payment_term_id', 
                 'sale_payment_term_id.line_ids', 'purchase_payment_term_id.line_ids',
                 'confirmation_date', 'rts_current', 'eta_current', 'production_start_current')
    def _compute_payment_milestones(self):
        """Compute payment milestone schedule display"""
        for deal in self:
            milestones = []
            
            # Customer payment milestones
            if deal.sale_payment_term_id:
                is_cad_term = (hasattr(deal.sale_payment_term_id, 'use_milestone_payments') 
                              and deal.sale_payment_term_id.use_milestone_payments)
                
                if is_cad_term:
                    for line in deal.sale_payment_term_id.line_ids.sorted('sequence'):
                        # Use milestone_type_id (not milestone_id)
                        if line.milestone_mode == 'milestone' and line.milestone_type_id:
                            milestone_type = line.milestone_type_id
                            
                            # Get actual date for this milestone
                            date = milestone_type.get_milestone_date(deal)
                            date_str = date.strftime('%Y-%m-%d') if date else 'TBD'
                            
                            # Build timing description
                            timing_desc = ""
                            if line.milestone_timing == 'before' and line.milestone_days > 0:
                                timing_desc = f"{line.milestone_days}d before "
                            elif line.milestone_timing == 'after' and line.milestone_days > 0:
                                timing_desc = f"{line.milestone_days}d after "
                            elif line.milestone_timing == 'on':
                                timing_desc = "on "
                            
                            milestones.append(
                                f"Customer: {line.value_amount:.1f}% {timing_desc}"
                                f"{milestone_type.name} ({date_str})"
                            )
                        else:
                            # Standard days-based line
                            days = line.nb_days or 0
                            milestones.append(
                                f"Customer: {line.value_amount:.1f}% after {days} days"
                            )
                else:
                    milestones.append(f"Customer: {deal.sale_payment_term_id.name}")
            
            # Supplier payment milestones
            if deal.purchase_payment_term_id:
                is_cad_term = (hasattr(deal.purchase_payment_term_id, 'use_milestone_payments')
                              and deal.purchase_payment_term_id.use_milestone_payments)
                
                if is_cad_term:
                    for line in deal.purchase_payment_term_id.line_ids.sorted('sequence'):
                        if line.milestone_mode == 'milestone' and line.milestone_type_id:
                            milestone_type = line.milestone_type_id
                            
                            date = milestone_type.get_milestone_date(deal)
                            date_str = date.strftime('%Y-%m-%d') if date else 'TBD'
                            
                            timing_desc = ""
                            if line.milestone_timing == 'before' and line.milestone_days > 0:
                                timing_desc = f"{line.milestone_days}d before "
                            elif line.milestone_timing == 'after' and line.milestone_days > 0:
                                timing_desc = f"{line.milestone_days}d after "
                            elif line.milestone_timing == 'on':
                                timing_desc = "on "
                            
                            milestones.append(
                                f"Supplier: {line.value_amount:.1f}% {timing_desc}"
                                f"{milestone_type.name} ({date_str})"
                            )
                        else:
                            days = line.nb_days or 0
                            milestones.append(
                                f"Supplier: {line.value_amount:.1f}% after {days} days"
                            )
                else:
                    milestones.append(f"Supplier: {deal.purchase_payment_term_id.name}")
            
            deal.payment_milestone_dates = '\n'.join(milestones) if milestones else 'No payment terms configured'
    
    # ============================================================
    # FINANCIAL DOCUMENT CREATION
    # ============================================================
    
    def _create_downpayment_requests(self):
        """Create downpayment requests based on payment terms
        
        REFACTORED: Includes duplicate prevention and better logging
        """
        self.ensure_one()
        
        # SAFEGUARD: Check if DPs already exist
        existing_dps = self.env['dm.downpayment.request'].search_count([
            ('deal_id', '=', self.id)
        ])
        
        if existing_dps > 0:
            _logger.warning(
                f"_create_downpayment_requests called for {self.name} "
                f"but {existing_dps} DPs already exist - aborting"
            )
            return  # Exit early
        
        _logger.info(f"Creating downpayment requests for deal {self.name}")
        
        # Check allocation status (optional warning)
        if hasattr(self, 'allocation_status'):
            if self.allocation_status == 'unallocated':
                _logger.warning(
                    f"Creating DPs for unallocated deal {self.name} - "
                    f"milestone dates may be estimated"
                )
        
        DP = self.env['dm.downpayment.request']
        
        # Customer downpayment (Sales)
        if self.sale_payment_term_id:
            if hasattr(self.sale_payment_term_id, 'line_ids'):
                dp_lines = self.sale_payment_term_id.line_ids.filtered('is_downpayment')
                
                for dp_line in dp_lines:
                    # Calculate amount
                    if dp_line.value == 'percent':
                        percentage = dp_line.value_amount
                        amount = self.total_value * (percentage / 100.0)
                    else:
                        percentage = 0.0
                        amount = dp_line.value_amount
                    
                    # Calculate due date
                    due_date = self._calculate_payment_date(dp_line, is_supplier=False)
                    
                    # Determine milestone trigger
                    milestone_trigger = 'confirmed'  # Default for customer
                    milestone_days = 0
                    
                    if dp_line.milestone_mode == 'milestone' and dp_line.milestone_type_id:
                        code_map = {
                            'order_conf': 'confirmed',
                            'prod_start': 'production_start',
                            'rts': 'rts',
                            'loading': 'loading',
                            'etd': 'etd',
                            'eta': 'eta',
                        }
                        milestone_trigger = code_map.get(
                            dp_line.milestone_type_id.milestone_code, 
                            'confirmed'
                        )
                        
                        if dp_line.milestone_timing == 'before':
                            milestone_days = -abs(dp_line.milestone_days or 0)
                        elif dp_line.milestone_timing == 'after':
                            milestone_days = abs(dp_line.milestone_days or 0)
                        else:
                            milestone_days = 0
                    
                    _logger.info(
                        f"  Creating customer DP: {percentage}% = ${amount:.2f}, "
                        f"due {due_date}, trigger={milestone_trigger}"
                    )
                    
                    DP.create({
                        'request_type': 'customer',
                        'deal_id': self.id,
                        'percentage': percentage,
                        'amount_requested': amount,
                        'due_date': due_date or fields.Date.today(),
                        'milestone_trigger': milestone_trigger,
                        'milestone_days': milestone_days,
                        'payment_term_line_id': dp_line.id,
                    })
        
        # Supplier downpayment (Purchase)
        if self.purchase_payment_term_id:
            if hasattr(self.purchase_payment_term_id, 'line_ids'):
                dp_lines = self.purchase_payment_term_id.line_ids.filtered('is_downpayment')
                
                for dp_line in dp_lines:
                    # Calculate amount
                    if dp_line.value == 'percent':
                        percentage = dp_line.value_amount
                        amount = self.purchase_total * (percentage / 100.0)
                    else:
                        percentage = 0.0
                        amount = dp_line.value_amount
                    
                    # Calculate due date
                    due_date = self._calculate_payment_date(dp_line, is_supplier=True)
                    
                    # Determine milestone trigger
                    milestone_trigger = 'production_start'  # Default for supplier
                    milestone_days = -14  # Default 14 days before
                    
                    if dp_line.milestone_mode == 'milestone' and dp_line.milestone_type_id:
                        code_map = {
                            'order_conf': 'confirmed',
                            'prod_start': 'production_start',
                            'rts': 'rts',
                            'loading': 'loading',
                            'etd': 'etd',
                            'eta': 'eta',
                        }
                        milestone_trigger = code_map.get(
                            dp_line.milestone_type_id.milestone_code, 
                            'production_start'
                        )
                        
                        if dp_line.milestone_timing == 'before':
                            milestone_days = -abs(dp_line.milestone_days or 0)
                        elif dp_line.milestone_timing == 'after':
                            milestone_days = abs(dp_line.milestone_days or 0)
                        else:
                            milestone_days = 0
                    
                    _logger.info(
                        f"  Creating supplier DP: {percentage}% = ${amount:.2f}, "
                        f"due {due_date}, trigger={milestone_trigger}"
                    )
                    
                    DP.create({
                        'request_type': 'supplier',
                        'deal_id': self.id,
                        'percentage': percentage,
                        'amount_requested': amount,
                        'due_date': due_date or fields.Date.today(),
                        'milestone_trigger': milestone_trigger,
                        'milestone_days': milestone_days,
                        'payment_term_line_id': dp_line.id,
                    })
        
        _logger.info(f"Downpayment request creation completed for {self.name}")
    
    def _create_invoice_split_config(self):
        """Create invoice split configuration"""
        self.ensure_one()
        
        if not self.invoice_split_config_id:
            ISC = self.env['dm.invoice.split.config']
            
            config = ISC.create({
                'deal_id': self.id,
                'split_type': 'custom',
            })
            
            self.invoice_split_config_id = config
    
    def _generate_cash_flow_projection(self):
        """Generate cash flow projection based on payment terms"""
        self.ensure_one()
        
        CashFlow = self.env['dm.cash_flow']
        
        # Clear existing projections
        self.cash_flow_projection.unlink()
        
        projections = []
        
        # Customer payments (inflows)
        if self.sale_payment_term_id:
            for line in self.sale_payment_term_id.line_ids:
                amount = self.total_value * (line.value_amount / 100.0) if line.value == 'percent' else line.value_amount
                date = self._calculate_payment_date(line)
                
                if date:
                    projections.append({
                        'deal_id': self.id,
                        'date': date,
                        'type': 'inflow',
                        'category': 'customer_payment',
                        'description': f"Customer payment - {line.milestone_type_id.name if hasattr(line, 'milestone_type_id') and line.milestone_type_id else 'Standard'}",
                        'amount': amount,
                        'currency_id': self.currency_id.id,
                    })
        
        # Supplier payments (outflows)
        if self.purchase_payment_term_id:
            for line in self.purchase_payment_term_id.line_ids:
                amount = self.purchase_total * (line.value_amount / 100.0) if line.value == 'percent' else line.value_amount
                date = self._calculate_payment_date(line, is_supplier=True)
                
                if date:
                    projections.append({
                        'deal_id': self.id,
                        'date': date,
                        'type': 'outflow',
                        'category': 'supplier_payment',
                        'description': f"Supplier payment - {line.milestone_type_id.name if hasattr(line, 'milestone_type_id') and line.milestone_type_id else 'Standard'}",
                        'amount': amount,
                        'currency_id': self.currency_id.id,
                    })
        
        # Create projection records
        for proj in sorted(projections, key=lambda x: x['date']):
            CashFlow.create(proj)
    
    def _calculate_payment_date(self, payment_line, is_supplier=False):
        """Calculate payment date based on milestone
        
        REFACTORED: Works with or without dm_production/dm_shipment installed
        """
        # Check if this is a milestone-based payment line
        if (hasattr(payment_line, 'milestone_mode') 
            and payment_line.milestone_mode == 'milestone'
            and hasattr(payment_line, 'milestone_type_id')
            and payment_line.milestone_type_id):
            
            # Use milestone type's method to get the date
            base_date = payment_line.milestone_type_id.get_milestone_date(self)
            
            if base_date:
                # Apply timing offset
                if hasattr(payment_line, 'milestone_timing'):
                    if payment_line.milestone_timing == 'before':
                        return base_date - timedelta(days=payment_line.milestone_days or 0)
                    elif payment_line.milestone_timing == 'after':
                        return base_date + timedelta(days=payment_line.milestone_days or 0)
                return base_date
        
        # Fallback to standard days from today
        days = payment_line.nb_days if hasattr(payment_line, 'nb_days') else 30
        return fields.Date.today() + timedelta(days=days)
    
    # ============================================================
    # SMART BUTTON ACTIONS
    # ============================================================
    
    def action_view_downpayments(self):
        """View downpayment requests - active ones by default"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Downpayment Requests'),
            'res_model': 'dm.downpayment.request',
            'view_mode': 'tree,form',
            'domain': [('deal_id', '=', self.id)],
            'context': {
                'default_deal_id': self.id,
                'search_default_active': 1,  # Activate "Active" filter by default
            }
        }
    
    def action_view_invoices(self):
        """View invoices"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Invoices'),
            'res_model': 'account.move',
            'view_mode': 'tree,form',
            'domain': [('dm_deal_id', '=', self.id)],
            'context': {'default_dm_deal_id': self.id}
        }
    
    def action_view_cash_flow(self):
        """View cash flow projection"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Cash Flow Projection'),
            'res_model': 'dm.cash_flow',
            'view_mode': 'tree,form,pivot,graph',
            'domain': [('deal_id', '=', self.id)],
            'context': {'default_deal_id': self.id}
        }
    
    def action_generate_invoices(self):
        """Generate invoices based on loading confirmation"""
        self.ensure_one()
        
        # Check for shipment via allocations
        has_shipment = False
        if hasattr(self, 'allocation_ids'):
            ship_allocations = self.allocation_ids.filtered(
                lambda a: a.allocation_type == 'deal_to_shipment'
                and a.state in ['active', 'completed']
            )
            has_shipment = bool(ship_allocations)
        
        if not has_shipment:
            raise UserError(_(
                'No shipment found. Invoices are generated after loading confirmation.'
            ))
        
        if self.invoice_split_config_id:
            return self.invoice_split_config_id.action_generate_invoices()
        else:
            # Generate standard invoice
            wizard = self.env['dm.invoice.generation.wizard'].create({
                'deal_id': self.id,
                'generate_split': False,
            })
            
            return {
                'name': _('Generate Invoice'),
                'type': 'ir.actions.act_window',
                'res_model': 'dm.invoice.generation.wizard',
                'res_id': wizard.id,
                'view_mode': 'form',
                'target': 'new',
            }
    
    # ============================================================
    # UTILITY METHODS
    # ============================================================
    
    @api.model
    def _check_module_installed(self, module_name):
        """Check if a module is installed
        
        Returns: True if installed, False otherwise
        """
        module = self.env['ir.module.module'].search([
            ('name', '=', module_name),
            ('state', '=', 'installed')
        ], limit=1)
        
        return bool(module)