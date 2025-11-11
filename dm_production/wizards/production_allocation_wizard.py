# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProductionAllocationWizard(models.TransientModel):
    """
    Production Allocation Wizard
    
    Allocates deals to production runs with proper validation.
    """
    _name = 'dm.production.allocation.wizard'
    _description = 'Production Allocation Wizard'
    
    deal_ids = fields.Many2many(
        'dm.deal',
        string='Deals',
        required=True,
        help='Deals to allocate to production'
    )
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        domain=[('state', 'in', ['draft', 'confirmed'])],
        help='Existing production run to allocate to'
    )
    
    create_new_pr = fields.Boolean(
        string='Create New Production Run',
        default=True
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('supplier_rank', '>', 0)],
        help='Supplier for new production run'
    )
    
    date_strategy = fields.Selection([
        ('earliest_start_latest_finish', 'Start Earliest, Finish Latest (Recommended)'),
        ('earliest_both', 'Start & Finish with Earliest Deal'),
        ('latest_both', 'Start & Finish with Latest Deal'),
        ('manual', 'Manual Entry')
    ], string='Date Strategy',
       default='earliest_start_latest_finish',
       help='How to calculate production dates from multiple deals')
    
    production_start_date = fields.Date(
        string='Production Start',
        help='Planned production start date'
    )
    
    rts_date = fields.Date(
        string='Target RTS Date',
        help='Target ready to ship date'
    )
    
    # Display fields for validation feedback
    supplier_warning = fields.Html(
        string='Supplier Check',
        compute='_compute_supplier_warning',
        sanitize=False
    )
    
    date_info = fields.Html(
        string='Date Calculation',
        compute='_compute_date_info',
        sanitize=False
    )
    
    # =====================================================
    # DEFAULT METHOD - Load deals from context
    # =====================================================
    
    @api.model
    def default_get(self, fields_list):
        """Pre-populate deals from context (selected records)"""
        res = super().default_get(fields_list)
        
        # Get active_ids from context (selected deals in tree view)
        active_ids = self.env.context.get('active_ids', [])
        active_model = self.env.context.get('active_model')
        
        if active_model == 'dm.deal' and active_ids:
            # Filter out already allocated deals
            deals = self.env['dm.deal'].browse(active_ids)
            
            # Check which deals are already allocated to active production
            unallocated = deals.filtered(lambda d: not any(
                a.allocation_type == 'production' 
                and a.state == 'active'
                and a.production_run_id
                and a.production_run_id.state != 'cancelled'
                for a in d.allocation_ids
            ))
            
            if unallocated:
                res['deal_ids'] = [(6, 0, unallocated.ids)]
            else:
                # All selected deals already allocated - show warning but include them
                res['deal_ids'] = [(6, 0, active_ids)]
            
            _logger.info(f"Wizard initialized with {len(active_ids)} deals from context")
            
            # AUTO-POPULATE supplier and dates from deals
            if unallocated or deals:
                deal_set = unallocated if unallocated else deals
                
                # Auto-populate supplier
                suppliers = deal_set.mapped('supplier_id').filtered(lambda s: s)
                if len(suppliers) == 1:
                    res['supplier_id'] = suppliers[0].id
                
                # Auto-populate dates based on default strategy
                date_strategy = res.get('date_strategy', 'earliest_start_latest_finish')
                
                if date_strategy != 'manual':
                    prod_starts = []
                    rts_dates = []
                    
                    for deal in deal_set:
                        # Production start (try current first, then requested)
                        if hasattr(deal, 'production_start_current') and deal.production_start_current:
                            prod_starts.append(deal.production_start_current)
                        elif hasattr(deal, 'production_start_requested') and deal.production_start_requested:
                            prod_starts.append(deal.production_start_requested)
                        
                        # RTS date (try current first, then requested)
                        if hasattr(deal, 'rts_current') and deal.rts_current:
                            rts_dates.append(deal.rts_current)
                        elif hasattr(deal, 'rts_requested') and deal.rts_requested:
                            rts_dates.append(deal.rts_requested)
                    
                    # Apply date strategy
                    if prod_starts:
                        if date_strategy == 'earliest_start_latest_finish':
                            res['production_start_date'] = min(prod_starts)
                        elif date_strategy == 'earliest_both':
                            res['production_start_date'] = min(prod_starts)
                        elif date_strategy == 'latest_both':
                            res['production_start_date'] = max(prod_starts)
                    
                    if rts_dates:
                        if date_strategy == 'earliest_start_latest_finish':
                            res['rts_date'] = max(rts_dates)
                        elif date_strategy == 'earliest_both':
                            res['rts_date'] = min(rts_dates)
                        elif date_strategy == 'latest_both':
                            res['rts_date'] = max(rts_dates)
                    
                    _logger.info(
                        f"Auto-populated wizard: supplier={res.get('supplier_id')}, "
                        f"prod_start={res.get('production_start_date')}, "
                        f"rts={res.get('rts_date')}"
                    )
        
        return res
    
    # =====================================================
    # ONCHANGE - Auto-populate supplier and dates
    # =====================================================
    
    @api.onchange('deal_ids', 'create_new_pr', 'date_strategy')
    def _onchange_deal_ids_and_strategy(self):
        """Auto-populate supplier and dates from deals when creating new PR"""
        if not self.create_new_pr or not self.deal_ids:
            return
        
        # Auto-populate supplier
        suppliers = self.deal_ids.mapped('supplier_id').filtered(lambda s: s)
        if len(suppliers) == 1:
            self.supplier_id = suppliers[0]
        
        # Auto-populate dates based on strategy (but not for manual)
        if self.date_strategy and self.date_strategy != 'manual':
            dates = self._calculate_dates_from_deals()
            
            if dates['prod_starts']:
                earliest_start = min(dates['prod_starts'])
                latest_start = max(dates['prod_starts'])
                
                if self.date_strategy == 'earliest_start_latest_finish':
                    self.production_start_date = earliest_start
                elif self.date_strategy == 'earliest_both':
                    self.production_start_date = earliest_start
                elif self.date_strategy == 'latest_both':
                    self.production_start_date = latest_start
            
            if dates['rts_dates']:
                earliest_rts = min(dates['rts_dates'])
                latest_rts = max(dates['rts_dates'])
                
                if self.date_strategy == 'earliest_start_latest_finish':
                    self.rts_date = latest_rts
                elif self.date_strategy == 'earliest_both':
                    self.rts_date = earliest_rts
                elif self.date_strategy == 'latest_both':
                    self.rts_date = latest_rts
    
    # =====================================================
    # COMPUTED FIELDS
    # =====================================================
    
    @api.depends('deal_ids', 'supplier_id', 'create_new_pr')
    def _compute_supplier_warning(self):
        """Check supplier consistency across selected deals"""
        for wizard in self:
            if not wizard.deal_ids:
                wizard.supplier_warning = ''
                continue
            
            # Get unique suppliers from deals
            suppliers = wizard.deal_ids.mapped('supplier_id').filtered(lambda s: s)
            
            if not suppliers:
                wizard.supplier_warning = '''
                    <div style="padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107;">
                        <strong>⚠️ No Supplier Set</strong><br/>
                        None of the selected deals have a supplier assigned.
                    </div>
                '''
            elif len(suppliers) == 1:
                wizard.supplier_warning = f'''
                    <div style="padding: 10px; background: #d4edda; border-left: 4px solid #28a745;">
                        <strong>✓ Supplier Consistent</strong><br/>
                        All deals are for: <strong>{suppliers[0].name}</strong>
                    </div>
                '''
            else:
                supplier_list = '<br/>'.join([f'• {s.name}' for s in suppliers])
                wizard.supplier_warning = f'''
                    <div style="padding: 10px; background: #f8d7da; border-left: 4px solid #dc3545;">
                        <strong>✗ Multiple Suppliers Detected</strong><br/>
                        Selected deals have different suppliers:<br/>
                        {supplier_list}<br/><br/>
                        <strong>Production runs must contain deals from a single supplier.</strong>
                    </div>
                '''
    
    @api.depends('deal_ids', 'date_strategy', 'create_new_pr')
    def _compute_date_info(self):
        """Show date calculation based on strategy"""
        for wizard in self:
            if not wizard.deal_ids or not wizard.create_new_pr:
                wizard.date_info = ''
                continue
            
            dates = wizard._calculate_dates_from_deals()
            
            if not dates['prod_starts'] and not dates['rts_dates']:
                wizard.date_info = '''
                    <div style="padding: 10px; background: #fff3cd; border-left: 4px solid #ffc107;">
                        <strong>⚠️ No Dates Found</strong><br/>
                        Selected deals have no production start or RTS dates set.
                    </div>
                '''
                continue
            
            # Build info message based on strategy
            if wizard.date_strategy == 'manual':
                wizard.date_info = '''
                    <div style="padding: 10px; background: #d1ecf1; border-left: 4px solid #17a2b8;">
                        <strong>ℹ️ Manual Entry Mode</strong><br/>
                        Please enter dates manually below.
                    </div>
                '''
            else:
                info_parts = ['<div style="padding: 10px; background: #d4edda; border-left: 4px solid #28a745;">']
                info_parts.append('<strong>📅 Date Calculation</strong><br/>')
                
                if dates['prod_starts']:
                    earliest_start = min(dates['prod_starts'])
                    latest_start = max(dates['prod_starts'])
                    info_parts.append(f'Production Start Range: {earliest_start} to {latest_start}<br/>')
                
                if dates['rts_dates']:
                    earliest_rts = min(dates['rts_dates'])
                    latest_rts = max(dates['rts_dates'])
                    info_parts.append(f'RTS Range: {earliest_rts} to {latest_rts}<br/>')
                
                info_parts.append('<br/><strong>Selected Strategy:</strong><br/>')
                
                if wizard.date_strategy == 'earliest_start_latest_finish':
                    if dates['prod_starts']:
                        info_parts.append(f'• Start: {min(dates["prod_starts"])} (earliest)<br/>')
                    if dates['rts_dates']:
                        info_parts.append(f'• Finish: {max(dates["rts_dates"])} (latest)')
                elif wizard.date_strategy == 'earliest_both':
                    if dates['prod_starts']:
                        info_parts.append(f'• Start: {min(dates["prod_starts"])} (earliest)<br/>')
                    if dates['rts_dates']:
                        info_parts.append(f'• Finish: {min(dates["rts_dates"])} (earliest)')
                elif wizard.date_strategy == 'latest_both':
                    if dates['prod_starts']:
                        info_parts.append(f'• Start: {max(dates["prod_starts"])} (latest)<br/>')
                    if dates['rts_dates']:
                        info_parts.append(f'• Finish: {max(dates["rts_dates"])} (latest)')
                
                info_parts.append('</div>')
                wizard.date_info = ''.join(info_parts)
    
    # =====================================================
    # HELPER METHODS
    # =====================================================
    
    def _calculate_dates_from_deals(self):
        """
        Extract production start and RTS dates from selected deals.
        
        Returns:
            dict: {
                'prod_starts': [date1, date2, ...],
                'rts_dates': [date1, date2, ...]
            }
        """
        self.ensure_one()
        
        prod_starts = []
        rts_dates = []
        
        for deal in self.deal_ids:
            # Production start (try current first, then requested)
            if hasattr(deal, 'production_start_current') and deal.production_start_current:
                prod_starts.append(deal.production_start_current)
            elif hasattr(deal, 'production_start_requested') and deal.production_start_requested:
                prod_starts.append(deal.production_start_requested)
            
            # RTS date (try current first, then requested)
            if hasattr(deal, 'rts_current') and deal.rts_current:
                rts_dates.append(deal.rts_current)
            elif hasattr(deal, 'rts_requested') and deal.rts_requested:
                rts_dates.append(deal.rts_requested)
        
        return {
            'prod_starts': prod_starts,
            'rts_dates': rts_dates,
        }
    
    # =====================================================
    # CONSTRAINTS
    # =====================================================
    
    @api.constrains('deal_ids', 'supplier_id', 'create_new_pr')
    def _check_supplier_consistency(self):
        """Validate supplier consistency"""
        for wizard in self:
            if not wizard.deal_ids or not wizard.create_new_pr:
                continue
            
            suppliers = wizard.deal_ids.mapped('supplier_id').filtered(lambda s: s)
            
            if len(suppliers) > 1:
                raise ValidationError(_(
                    'Cannot allocate deals with different suppliers to same production run.\n\n'
                    'Suppliers in selection:\n%s\n\n'
                    'Please select deals from a single supplier.'
                ) % '\n'.join([f'• {s.name}' for s in suppliers]))
            
            # If creating new PR with specified supplier, it must match deals
            if wizard.supplier_id and suppliers and wizard.supplier_id != suppliers[0]:
                raise ValidationError(_(
                    'Selected supplier (%s) does not match deals supplier (%s)'
                ) % (wizard.supplier_id.name, suppliers[0].name))
    
    # =====================================================
    # ACTION METHODS
    # =====================================================
    
    def action_allocate(self):
        """Allocate deals to production with validation"""
        self.ensure_one()
        
        # Validate wizard inputs
        if self.create_new_pr:
            if not self.supplier_id:
                raise UserError(_('Supplier is required for new production run'))
            
            if self.date_strategy == 'manual':
                if not self.production_start_date or not self.rts_date:
                    raise UserError(_('Please enter production start and RTS dates'))
        else:
            if not self.production_run_id:
                raise UserError(_('Please select a production run'))
        
        # Check for existing active allocations
        Allocation = self.env['dm.allocation']
        ProductionRun = self.env['dm.production.run']
        
        for deal in self.deal_ids:
            active_pr_allocs = Allocation.search([
                ('deal_id', '=', deal.id),
                ('allocation_type', '=', 'production'),
                ('state', '=', 'active'),
            ])
            
            # Filter to only those with valid, non-cancelled PRs
            valid_allocs = active_pr_allocs.filtered(
                lambda a: a.production_run_id 
                and a.production_run_id.exists() 
                and a.production_run_id.state != 'cancelled'
            )
            
            if valid_allocs:
                pr_names = ', '.join(valid_allocs.mapped('production_run_id.name'))
                raise UserError(_(
                    'Deal %s is already allocated to production run(s): %s. '
                    'Cannot create duplicate active allocation.'
                ) % (deal.name, pr_names))
        
        # Create or get production run
        if self.create_new_pr:
            pr_vals = {
                'supplier_id': self.supplier_id.id,
            }
            
            # Use three-layer date fields
            if hasattr(ProductionRun, 'production_start_current'):
                # Set both requested and current
                if self.production_start_date:
                    pr_vals['production_start_requested'] = self.production_start_date
                    pr_vals['production_start_current'] = self.production_start_date
                if self.rts_date:
                    pr_vals['rts_requested'] = self.rts_date
                    pr_vals['rts_current'] = self.rts_date
            else:
                # Fallback to legacy fields
                if self.production_start_date:
                    pr_vals['production_start_date'] = self.production_start_date
                if self.rts_date:
                    pr_vals['rts_date'] = self.rts_date
            
            pr = ProductionRun.create(pr_vals)
            _logger.info(f"Created production run {pr.name} for supplier {self.supplier_id.name}")
        else:
            pr = self.production_run_id
        
        # Create allocations and production lines
        allocations_created = 0
        
        for deal in self.deal_ids:
            # Create allocation
            allocation = Allocation.create({
                'deal_id': deal.id,
                'allocation_type': 'production',
                'production_run_id': pr.id,
                'state': 'active',
            })
            allocations_created += 1
            
            # Auto-create production lines from deal lines
            self._create_production_lines_for_deal(pr, deal)
            
            # Update deal state ONLY if BOTH PR and Shipment allocated
            if deal.state == 'confirmed':
                # Check if shipment also allocated
                shipment_allocated = any(
                    a.allocation_type == 'shipment' and a.state == 'active'
                    for a in deal.allocation_ids
                )
                
                if shipment_allocated:
                    deal.write({'state': 'allocated'})
                    _logger.info(f"Deal {deal.name} state → 'allocated' (both PR and Shipment)")
                else:
                    _logger.info(f"Deal {deal.name} remains 'confirmed' (only PR allocated)")
        
        _logger.info(f"✓ Allocated {allocations_created} deal(s) to PR {pr.name}")
        
        # Return to PR form
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Run'),
            'res_model': 'dm.production.run',
            'res_id': pr.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def _create_production_lines_for_deal(self, production_run, deal):
        """Auto-create production lines from deal lines"""
        _logger.info(f"=== CREATE PR LINES START ===")
        _logger.info(f"PR: {production_run.name} (ID: {production_run.id})")
        _logger.info(f"Deal: {deal.name} (ID: {deal.id})")
        _logger.info(f"Deal lines count: {len(deal.line_ids)}")
        
        if not deal.line_ids:
            _logger.warning(f"Deal {deal.name} has NO LINES!")
            return []
        
        lines_created = []
        
        for deal_line in deal.line_ids:
            _logger.info(f"\n--- Processing deal line {deal_line.id} ---")
            _logger.info(f"Product: {deal_line.product_id.name if deal_line.product_id else 'MISSING'}")
            _logger.info(f"Packaging: {deal_line.product_packaging_id.name if deal_line.product_packaging_id else 'MISSING'}")
            _logger.info(f"Qty packaging: {deal_line.quantity_packaging}")
            
            # Validation checks
            if not deal_line.product_id:
                _logger.error(f"SKIP: No product_id on line {deal_line.id}")
                continue
                
            if not deal_line.product_packaging_id:
                _logger.error(f"SKIP: No product_packaging_id on line {deal_line.id}")
                continue
                
            if not deal_line.quantity_packaging or deal_line.quantity_packaging <= 0:
                _logger.error(f"SKIP: Zero/negative quantity on line {deal_line.id}: {deal_line.quantity_packaging}")
                continue
            
            try:
                pr_line = self.env['dm.production.line'].create({
                    'production_run_id': production_run.id,
                    'deal_id': deal.id,
                    'deal_line_id': deal_line.id,
                    'product_id': deal_line.product_id.id,
                    'product_packaging_id': deal_line.product_packaging_id.id,
                    'quantity_ordered': deal_line.quantity_packaging,
                    'quantity_produced': 0.0,
                    'sequence': deal_line.sequence,
                })
                lines_created.append(pr_line)
                _logger.info(f"✓ Created PR line {pr_line.id}")
                
            except Exception as e:
                _logger.error(f"✗ FAILED to create PR line: {e}", exc_info=True)
                continue
        
        _logger.info(f"=== CREATED {len(lines_created)} PR LINES ===")
        
        return lines_created