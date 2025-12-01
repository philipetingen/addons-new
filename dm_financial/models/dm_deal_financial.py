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
    
    # NOTE: Other milestone date fields (production_start_current, loading_current,
    # etd_current, etc.) are defined in dm_deal_milestones.py
    # This module only receives CASCADE updates for those fields
    
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
    
    # Cash flow fields - DISABLED (Phase 1)
    # cash_flow_projection = fields.One2many(
    #     'dm.cash_flow',
    #     'deal_id',
    #     string='Cash Flow Projection'
    # )
    
    total_receivable = fields.Monetary(
        string='Total Receivable',
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    
    total_payable = fields.Monetary(
        string='Total Payable',
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    
    gross_margin = fields.Monetary(
        string='Gross Margin',
        compute='_compute_financial_summary',
        store=True,
        currency_field='currency_id'
    )
    
    gross_margin_percent = fields.Float(
        string='Gross Margin %',
        compute='_compute_financial_summary',
        store=True,
        digits=(5, 2)
    )
    
    # Payment terms
    sale_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Customer Payment Terms',
        tracking=True,
        help='CAD payment term for customer'
    )
    
    purchase_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Supplier Payment Terms',
        tracking=True,
        help='CAD payment term for supplier'
    )
    
    payment_milestone_dates = fields.Text(
        string='Payment Milestones',
        compute='_compute_payment_milestones',
        help='Computed payment milestone schedule'
    )
    
    # NOTE: total_value and purchase_total removed - use amount_untaxed_sale 
    # and amount_untaxed_purchase from dm_deal core instead
    
    # ============================================================
    # MODULE AVAILABILITY CHECKS
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
    
    # ============================================================
    # COMPUTE METHODS FOR MILESTONE DATES (ORCHESTRATOR-AWARE)
    # ============================================================
    
    @api.depends('allocation_ids', 'allocation_ids.state', 
                 'allocation_ids.allocation_type', 'allocation_ids.production_run_id',
                 'rts_current', 'rts_requested', 'confirmation_date')
    def _compute_production_dates(self):
        """Get production dates via orchestrator allocations OR estimate from RTS
        
        REFACTORED: Uses allocation_ids instead of direct production_run_ids access
        FIX: Uses 'production' allocation type (not 'deal_to_production')
        """
        for deal in self:
            # Check if dm_production module is installed
            dm_production_installed = self._check_module_installed('dm_production')
            
            if dm_production_installed and hasattr(deal, 'allocation_ids'):
                # Get production runs via allocations (orchestrator pattern)
                # FIX: Changed from 'deal_to_production' to 'production'
                pr_allocations = deal.allocation_ids.filtered(
                    lambda a: a.allocation_type == 'production'
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
                        
                        if hasattr(deal, 'production_start_current') and start_dates:
                            deal.production_start_current = min(start_dates)
                            _logger.info(
                                f"Production start for {deal.name}: {deal.production_start_current} "
                                f"(from {len(active_runs)} production run(s))"
                            )
                            continue
            
            # FALLBACK: Estimate from RTS date (works with or without dm_production)
            if hasattr(deal, 'rts_actual'):
                rts_date = deal.rts_actual or deal.rts_current or deal.rts_requested
                if rts_date and hasattr(deal, 'production_start_current'):
                    deal.production_start_current = rts_date - timedelta(days=14)
                    _logger.debug(
                        f"Estimated production start for {deal.name}: {deal.production_start_current} "
                        f"(14 days before RTS {rts_date})"
                    )
            elif deal.confirmation_date and hasattr(deal, 'production_start_current'):
                # Final fallback: confirmation date + 7 days
                deal.production_start_current = deal.confirmation_date + timedelta(days=7)
                _logger.debug(
                    f"Fallback production start for {deal.name}: {deal.production_start_current} "
                    f"(7 days after confirmation)"
                )
    
    @api.depends('allocation_ids', 'allocation_ids.state',
                 'allocation_ids.allocation_type', 'allocation_ids.shipment_id')
    def _compute_shipment_dates(self):
        """Get shipment dates via orchestrator allocations
        
        REFACTORED: Uses allocation_ids instead of direct shipment_ids access
        FIX: Uses 'shipment' allocation type (not 'deal_to_shipment')
        """
        for deal in self:
            # Check if dm_shipment module is installed
            dm_shipment_installed = self._check_module_installed('dm_shipment')
            
            if dm_shipment_installed and hasattr(deal, 'allocation_ids'):
                # Get shipments via allocations (orchestrator pattern)
                # FIX: Changed from 'deal_to_shipment' to 'shipment'
                ship_allocations = deal.allocation_ids.filtered(
                    lambda a: a.allocation_type == 'shipment'
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
                            if hasattr(deal, 'loading_current'):
                                deal.loading_current = ship.loading_date
                            elif hasattr(deal, 'loading_date_current'):
                                deal.loading_date_current = ship.loading_date
                        elif hasattr(ship, 'loading_date_actual'):
                            if hasattr(deal, 'loading_current'):
                                deal.loading_current = ship.loading_date_actual
                            elif hasattr(deal, 'loading_date_current'):
                                deal.loading_date_current = ship.loading_date_actual
                        
                        # ETD
                        if hasattr(ship, 'etd'):
                            if hasattr(deal, 'etd_current'):
                                deal.etd_current = ship.etd
                        elif hasattr(ship, 'etd_current'):
                            if hasattr(deal, 'etd_current'):
                                deal.etd_current = ship.etd_current
                        
                        # Delivery date (use ETA as proxy)
                        if hasattr(ship, 'eta_actual'):
                            if hasattr(deal, 'delivery_current'):
                                deal.delivery_current = ship.eta_actual
                            elif hasattr(deal, 'delivery_date'):
                                deal.delivery_date = ship.eta_actual
                        elif hasattr(ship, 'eta_current'):
                            if hasattr(deal, 'delivery_current'):
                                deal.delivery_current = ship.eta_current
                            elif hasattr(deal, 'delivery_date'):
                                deal.delivery_date = ship.eta_current
                        elif hasattr(ship, 'eta'):
                            if hasattr(deal, 'delivery_current'):
                                deal.delivery_current = ship.eta
                            elif hasattr(deal, 'delivery_date'):
                                deal.delivery_date = ship.eta
                        
                        continue
            
            # No shipments or module not installed - clear fields if they exist
            if hasattr(deal, 'loading_current'):
                deal.loading_current = False
            elif hasattr(deal, 'loading_date_current'):
                deal.loading_date_current = False
            
            if hasattr(deal, 'etd_current'):
                deal.etd_current = False
            
            if hasattr(deal, 'delivery_current'):
                deal.delivery_current = False
            elif hasattr(deal, 'delivery_date'):
                deal.delivery_date = False
    
    # ============================================================
    # STATE CHANGE HOOKS (REFACTORED)
    # ============================================================
    
    def write(self, vals):
        """Override to handle state changes and trigger DP creation"""
        result = super(DmDeal, self).write(vals)
        
        # Trigger DP creation on confirmation
        if 'state' in vals:
            for deal in self:
                if deal.state == 'confirmed' and not deal.confirmation_date:
                    deal.confirmation_date = fields.Date.today()
                    
                    # Create downpayments if payment term configured
                    if deal.sale_payment_term_id or deal.purchase_payment_term_id:
                        deal._create_downpayment_requests()
        
        return result
    
    def action_confirm(self):
        """
        Confirm deal: SO and PO created/confirmed.
        
        Note: Downpayment creation is handled by write() hook on state change.
        This method only focuses on core confirmation logic.
        """
        result = super(DmDeal, self).action_confirm()
        
        # Set confirmation date if not already set
        for deal in self:
            if not deal.confirmation_date:
                deal.confirmation_date = fields.Date.today()
        
        return result
    
    # ============================================================
    # COMPUTE METHODS FOR FINANCIAL TRACKING
    # ============================================================
    
    # NOTE: _compute_deal_totals removed - dm_deal core already computes
    # amount_untaxed_sale and amount_untaxed_purchase
    
    @api.depends('downpayment_request_ids', 'invoice_ids')
    def _compute_financial_counts(self):
        """Count downpayments and invoices"""
        for deal in self:
            deal.downpayment_count = len(deal.downpayment_request_ids)
            # Count only active invoices
            active_invoices = deal.invoice_ids.filtered(lambda i: i.state != 'cancel')
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
            if hasattr(deal, 'sale_incoterm_id') and deal.sale_incoterm_id:
                if deal.sale_incoterm_id.code in ['CIF', 'CFR']:
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
        
        REFACTORED: 
        - Updated field names for dm_downpayment_request v2.0
        - payment_type instead of request_type
        - 'inbound'/'outbound' instead of 'customer'/'supplier'
        - Includes partner_id (now required)
        - Removed deprecated fields (milestone_trigger, milestone_days, payment_term_line_id)
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
        created_count = 0
        
        # Customer downpayment (Sales)
        if self.sale_payment_term_id:
            if hasattr(self.sale_payment_term_id, 'line_ids'):
                dp_lines = self.sale_payment_term_id.line_ids.filtered('is_downpayment')
                
                for dp_line in dp_lines:
                    # Calculate amount
                    if dp_line.value == 'percent':
                        percentage = dp_line.value_amount
                        amount = self.amount_untaxed_sale * (percentage / 100.0)
                    else:
                        percentage = 0.0
                        amount = dp_line.value_amount
                    
                    # Skip zero amounts
                    if amount <= 0:
                        _logger.debug(f"Skipping zero-amount customer DP line")
                        continue
                    
                    # Calculate due date
                    due_date = self._calculate_payment_date(dp_line, is_supplier=False)
                    
                    _logger.info(
                        f"  Creating customer DP: {percentage}% = ${amount:.2f}, "
                        f"due {due_date}"
                    )
                    
                    dp_vals = {
                        'payment_type': 'inbound',
                        'deal_id': self.id,
                        'partner_id': self.customer_id.id,
                        'currency_id': self.currency_id.id,
                        'percentage': percentage,
                        'amount_requested': amount,
                        'due_date': due_date or fields.Date.today(),
                        'payment_term_id': self.sale_payment_term_id.id,
                    }
                    
                    # Add milestone_id if available
                    if hasattr(dp_line, 'milestone_type_id') and dp_line.milestone_type_id:
                        # Find or create payment milestone for this deal
                        milestone = self._get_or_create_payment_milestone(
                            dp_line.milestone_type_id,
                            'customer',
                            percentage,
                            amount
                        )
                        if milestone:
                            dp_vals['milestone_id'] = milestone.id
                    
                    try:
                        dp = DP.create(dp_vals)
                        created_count += 1
                        _logger.info(f"    Created DP: {dp.name}")
                    except Exception as e:
                        _logger.error(f"    Failed to create customer DP: {e}")
        
        # Supplier downpayment (Purchase)
        if self.purchase_payment_term_id:
            if hasattr(self.purchase_payment_term_id, 'line_ids'):
                dp_lines = self.purchase_payment_term_id.line_ids.filtered('is_downpayment')
                
                for dp_line in dp_lines:
                    # Calculate amount
                    if dp_line.value == 'percent':
                        percentage = dp_line.value_amount
                        amount = self.amount_untaxed_purchase * (percentage / 100.0)
                    else:
                        percentage = 0.0
                        amount = dp_line.value_amount
                    
                    # Skip zero amounts
                    if amount <= 0:
                        _logger.debug(f"Skipping zero-amount supplier DP line")
                        continue
                    
                    # Calculate due date
                    due_date = self._calculate_payment_date(dp_line, is_supplier=True)
                    
                    _logger.info(
                        f"  Creating supplier DP: {percentage}% = ${amount:.2f}, "
                        f"due {due_date}"
                    )
                    
                    dp_vals = {
                        'payment_type': 'outbound',
                        'deal_id': self.id,
                        'partner_id': self.supplier_id.id,
                        'currency_id': self.currency_id.id,
                        'percentage': percentage,
                        'amount_requested': amount,
                        'due_date': due_date or fields.Date.today(),
                        'payment_term_id': self.purchase_payment_term_id.id,
                    }
                    
                    # Add milestone_id if available
                    if hasattr(dp_line, 'milestone_type_id') and dp_line.milestone_type_id:
                        milestone = self._get_or_create_payment_milestone(
                            dp_line.milestone_type_id,
                            'supplier',
                            percentage,
                            amount
                        )
                        if milestone:
                            dp_vals['milestone_id'] = milestone.id
                    
                    try:
                        dp = DP.create(dp_vals)
                        created_count += 1
                        _logger.info(f"    Created DP: {dp.name}")
                    except Exception as e:
                        _logger.error(f"    Failed to create supplier DP: {e}")
        
        _logger.info(
            f"Downpayment request creation completed for {self.name}: "
            f"{created_count} DPs created"
        )
        
        # Post chatter message
        if created_count > 0:
            self.message_post(
                body=_(
                    "Created %d downpayment request(s) based on payment terms."
                ) % created_count,
                message_type='comment'
            )
    
    def _get_or_create_payment_milestone(self, milestone_type, payment_type, percentage, amount):
        """Get or create a payment milestone for this deal
        
        Args:
            milestone_type: dm.milestone.type record
            payment_type: 'customer' or 'supplier'
            percentage: percentage of deal value
            amount: calculated amount
            
        Returns:
            dm.payment.milestone record or False
        """
        self.ensure_one()
        
        PaymentMilestone = self.env.get('dm.payment.milestone')
        if not PaymentMilestone:
            _logger.debug("dm.payment.milestone model not available")
            return False
        
        # Check if milestone already exists for this deal/type/payment_type
        existing = PaymentMilestone.search([
            ('deal_id', '=', self.id),
            ('milestone_type_id', '=', milestone_type.id),
            ('payment_type', '=', payment_type),
        ], limit=1)
        
        if existing:
            return existing
        
        # Create new milestone
        try:
            milestone = PaymentMilestone.create({
                'deal_id': self.id,
                'milestone_type_id': milestone_type.id,
                'payment_type': payment_type,
                'percentage': percentage,
            })
            _logger.info(
                f"Created payment milestone {milestone.name} for deal {self.name}"
            )
            return milestone
        except Exception as e:
            _logger.warning(f"Failed to create payment milestone: {e}")
            return False
    
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
    
    # DISABLED - Phase 1 (dm.cash_flow model removed)
    # def _generate_cash_flow_projection(self):
    #     """Generate cash flow projection based on payment terms"""
    #     self.ensure_one()
    #     
    #     CashFlow = self.env['dm.cash_flow']
    #     
    #     # Clear existing projections
    #     self.cash_flow_projection.unlink()
    #     ... (method disabled)
    
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
            # FIX: Changed from 'deal_to_shipment' to 'shipment'
            ship_allocations = self.allocation_ids.filtered(
                lambda a: a.allocation_type == 'shipment'
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