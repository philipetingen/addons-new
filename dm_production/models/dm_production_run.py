# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmProductionRun(models.Model):
    """
    Production Run - Phase 3A Enhanced
    
    Phase 3 Features:
    - TEU and container totals from deals
    - Container summary display
    - Capacity validation before confirmation
    - Pre-allocation capacity checking
    
    Phase 3A NEW Features:
    - Capacity utilization percentage and color coding
    - Add deals action
    - Enhanced allocation helpers
    """
    _name = 'dm.production.run'
    _description = 'Production Run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'id desc'
    
    # ========================================================================
    # CORE FIELDS
    # ========================================================================
    
    name = fields.Char(
        string='Production Run',
        required=True,
        copy=False,
        default='New',
        tracking=True
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier/Manufacturer',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        tracking=True
    )
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_production', 'In Production'),  # ✅ Changed from 'production'
        ('qc_pending', 'QC Pending'),
        ('ready', 'Ready to Ship'),
        ('completed', 'Completed'),          # ✅ Changed from 'done'
        ('cancelled', 'Cancelled'),
    ], string='Status', default='draft', required=True, tracking=True)
    
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        default=lambda self: self.env.company
    )
    
    # ========================================================================
    # THREE-LAYER DATE MANAGEMENT
    # ========================================================================
    
    # Production Start dates
    production_start_requested = fields.Date(
        string='Production Start (Requested)',
        tracking=True,
        help='Original requested production start date'
    )
    
    production_start_current = fields.Date(
        string='Production Start (Current)',
        tracking=True,
        help='Current planned production start date'
    )
    
    production_start_actual = fields.Date(
        string='Production Start (Actual)',
        tracking=True,
        readonly=True,
        help='Actual production start date - CASCADEs to deals'
    )
    
    # RTS dates
    rts_requested = fields.Date(
        string='RTS (Requested)',
        tracking=True,
        help='Original requested ready-to-ship date'
    )
    
    rts_current = fields.Date(
        string='RTS (Current)',
        required=True,
        tracking=True,
        help='Current planned ready-to-ship date'
    )
    
    rts_actual = fields.Date(
        string='RTS (Actual)',
        tracking=True,
        readonly=True,
        help='Actual ready-to-ship date - CASCADEs to deals'
    )
    
    # ========================================================================
    # BACKWARD COMPATIBILITY FIELDS
    # ========================================================================
    
    production_start_date = fields.Date(
        string='Production Start',
        compute='_compute_backward_compat_dates',
        inverse='_inverse_production_start_date',
        store=False,
        tracking=True
    )
    
    rts_date = fields.Date(
        string='Ready to Ship',
        compute='_compute_backward_compat_dates',
        inverse='_inverse_rts_date',
        store=False,
        tracking=True,
        help='Target RTS date for this production run'
    )
    
    # ========================================================================
    # ALLOCATION RELATIONSHIPS
    # ========================================================================
    
    allocation_ids = fields.One2many(
        'dm.allocation',
        'production_run_id',
        string='Deal Allocations',
        help='Deals allocated to this production run'
    )
    
    deal_ids = fields.Many2many(
        'dm.deal',
        compute='_compute_deals',
        string='Deals',
        help='Deals in this production run'
    )
    
    deal_count = fields.Integer(
        compute='_compute_deal_count',
        string='Deal Count'
    )
    
    # ========================================================================
    # PHASE 3: TEU & CONTAINER TOTALS
    # ========================================================================
    
    total_teu = fields.Float(
        string='Total TEU',
        compute='_compute_totals',
        store=True,
        digits=(10, 2),
        help='Sum of TEU from all allocated deals'
    )
    
    total_containers = fields.Float(
        string='Total Containers',
        compute='_compute_totals',
        store=True,
        digits=(10, 2),
        help='Sum of containers from all allocated deals'
    )
    
    container_summary = fields.Char(
        string='Container Summary',
        compute='_compute_container_summary',
        help='e.g., "2×40HC + 1×20GP = 7.0 TEU"'
    )
    
    container_breakdown = fields.Text(
        string='Container Breakdown',
        compute='_compute_container_breakdown',
        help='Detailed breakdown by container type'
    )
    
    # ========================================================================
    # PHASE 3A: CAPACITY UTILIZATION DISPLAY
    # ========================================================================
    
    capacity_utilization_pct = fields.Float(
        string='Capacity Utilization %',
        compute='_compute_capacity_utilization',
        store=True,
        help='Percentage of vendor capacity used'
    )
    
    capacity_status_color = fields.Selection([
        ('green', 'Healthy (<80%)'),
        ('yellow', 'Near Limit (80-100%)'),
        ('red', 'Over Capacity (>100%)')
    ], string='Status Color', 
        compute='_compute_capacity_utilization', 
        store=True,
        help='Visual indicator for capacity status'
    )
    
    # Related field from capacity planning module (if installed)
    month_capacity_teu = fields.Float(
        string='Month Capacity (TEU)',
        help='Vendor capacity for this month (if capacity planning installed)'
    )
    
    # ========================================================================
    # NOTES
    # ========================================================================
    
    notes = fields.Text(string='Notes')

    # ========================================================================
    # PRODUCTION LINES (Phase 1)
    # ========================================================================
    
    line_ids = fields.One2many(
        'dm.production.line',
        'production_run_id',
        string='Production Lines',
        help='Production lines for this run'
    )
    
    line_count = fields.Integer(
        compute='_compute_line_count',
        string='Line Count'
    )
    
    # Totals from lines
    total_teu_from_lines = fields.Float(
        compute='_compute_line_totals',
        store=True,
        string='TEU (from Lines)',
        digits=(16, 6)
    )
    
    total_containers_from_lines = fields.Float(
        compute='_compute_line_totals',
        store=True,
        string='Containers (from Lines)',
        digits=(16, 6)
    )
    
    # ========================================================================
    # COMPUTED METHODS
    # ========================================================================
    
    @api.depends('allocation_ids', 'allocation_ids.deal_id', 'allocation_ids.state')
    def _compute_deals(self):
        """Get deals from active allocations"""
        for pr in self:
            active_allocations = pr.allocation_ids.filtered(
                lambda a: a.state in ['active', 'completed']
            )
            pr.deal_ids = active_allocations.mapped('deal_id')
    
    @api.depends('deal_ids')
    def _compute_deal_count(self):
        for pr in self:
            pr.deal_count = len(pr.deal_ids)
    
    # ========================================================================
    # BACKWARD COMPATIBILITY COMPUTES
    # ========================================================================
    
    @api.depends('production_start_current', 'rts_current')
    def _compute_backward_compat_dates(self):
        """Map old single-date fields to new three-layer dates"""
        for pr in self:
            pr.production_start_date = pr.production_start_current
            pr.rts_date = pr.rts_current
    
    def _inverse_production_start_date(self):
        """Write to production_start_current when old field updated"""
        for pr in self:
            if pr.production_start_date:
                pr.production_start_current = pr.production_start_date
    
    def _inverse_rts_date(self):
        """Write to rts_current when old field updated"""
        for pr in self:
            if pr.rts_date:
                pr.rts_current = pr.rts_date
    
    @api.depends('deal_ids', 'deal_ids.total_teu', 'deal_ids.total_containers')
    def _compute_totals(self):
        """
        Phase 3: Calculate total TEU and containers from allocated deals
        """
        for pr in self:
            total_teu = 0.0
            total_containers = 0.0
            
            for deal in pr.deal_ids:
                # Safe access with hasattr check
                if hasattr(deal, 'total_teu') and deal.total_teu:
                    total_teu += deal.total_teu
                
                if hasattr(deal, 'total_containers') and deal.total_containers:
                    total_containers += deal.total_containers
            
            pr.total_teu = total_teu
            pr.total_containers = total_containers
            
            _logger.debug(
                f"PR {pr.name}: {total_containers:.2f} containers = {total_teu:.2f} TEU"
            )
    
    @api.depends('total_teu', 'month_capacity_teu')
    def _compute_capacity_utilization(self):
        """
        Phase 3A: Calculate capacity utilization percentage and status color
        Gracefully handles when capacity planning module is not installed
        """
        for pr in self:
            # Check if capacity planning is available
            capacity_teu = 0.0
            
            # Try to get from vendor_capacity_id (dm_capacity_planning)
            if hasattr(pr, 'vendor_capacity_id') and pr.vendor_capacity_id:
                capacity_teu = pr.vendor_capacity_id.effective_capacity_teu
            # Fallback to month_capacity_teu if set manually
            elif pr.month_capacity_teu:
                capacity_teu = pr.month_capacity_teu
            
            # Calculate utilization
            if capacity_teu > 0:
                utilization = (pr.total_teu / capacity_teu) * 100
                pr.capacity_utilization_pct = utilization
                
                # Determine color
                if utilization >= 100:
                    pr.capacity_status_color = 'red'
                elif utilization >= 80:
                    pr.capacity_status_color = 'yellow'
                else:
                    pr.capacity_status_color = 'green'
            else:
                pr.capacity_utilization_pct = 0.0
                pr.capacity_status_color = 'green'  # No capacity tracking = green
    
    @api.depends('deal_ids', 'deal_ids.total_teu', 'deal_ids.total_containers', 'deal_ids.container_summary')
    def _compute_container_summary(self):
        """
        Phase 3: Generate container summary like "2×40HC + 1×20GP = 7.0 TEU"
        
        Note: dm.deal already has container_summary computed from lines.
        This aggregates summaries from multiple deals.
        """
        for pr in self:
            if not pr.deal_ids or pr.total_teu == 0:
                pr.container_summary = ''
                continue
            
            # If only one deal, use its summary
            if len(pr.deal_ids) == 1:
                deal = pr.deal_ids[0]
                pr.container_summary = deal.container_summary if hasattr(deal, 'container_summary') else f"{pr.total_teu:.1f} TEU"
                continue
            
            # Multiple deals - aggregate by container type from lines
            container_counts = {}
            
            for deal in pr.deal_ids:
                if hasattr(deal, 'line_ids'):
                    for line in deal.line_ids:
                        if hasattr(line, 'container_type_id') and line.container_type_id:
                            ct = line.container_type_id
                            containers = line.containers_required if hasattr(line, 'containers_required') else 0
                            
                            if ct.id not in container_counts:
                                container_counts[ct.id] = {
                                    'type': ct,
                                    'count': 0
                                }
                            container_counts[ct.id]['count'] += containers
            
            # Build summary string
            if not container_counts:
                pr.container_summary = f"{pr.total_teu:.1f} TEU"
            else:
                parts = []
                for data in sorted(container_counts.values(), 
                                   key=lambda x: x['type'].teu_factor or 0, 
                                   reverse=True):
                    ct = data['type']
                    count = data['count']
                    parts.append(f"{count:.1f}×{ct.code}")
                
                pr.container_summary = " + ".join(parts) + f" = {pr.total_teu:.1f} TEU"
    
    @api.depends('deal_ids', 'deal_ids.line_ids', 'deal_ids.line_ids.container_type_id')
    def _compute_container_breakdown(self):
        """
        Phase 3: Detailed breakdown by container type
        """
        for pr in self:
            if not pr.deal_ids:
                pr.container_breakdown = ''
                continue
            
            container_counts = {}
            
            for deal in pr.deal_ids:
                if hasattr(deal, 'line_ids'):
                    for line in deal.line_ids:
                        if hasattr(line, 'container_type_id') and line.container_type_id:
                            ct = line.container_type_id
                            containers = line.containers_required if hasattr(line, 'containers_required') else 0
                            teu = line.container_teu if hasattr(line, 'container_teu') else 0
                            
                            if ct.id not in container_counts:
                                container_counts[ct.id] = {
                                    'type': ct,
                                    'containers': 0,
                                    'teu': 0
                                }
                            container_counts[ct.id]['containers'] += containers
                            container_counts[ct.id]['teu'] += teu
            
            # Build breakdown text
            if not container_counts:
                pr.container_breakdown = 'No containers'
            else:
                lines = []
                for data in sorted(container_counts.values(), 
                                   key=lambda x: x['type'].teu_factor or 0, 
                                   reverse=True):
                    ct = data['type']
                    containers = data['containers']
                    teu = data['teu']
                    
                    # ✅ FIX: Use display_name instead of code
                    display = ct.display_name if ct.display_name else ct.name
                    lines.append(
                        f"• {display}: {containers:.1f} containers = {teu:.1f} TEU"
                    )
                pr.container_breakdown = "\n".join(lines)

    # ========================================================================
    # PRODUCTION LINE COMPUTATIONS (Phase 1)
    # ========================================================================
    
    @api.depends('line_ids')
    def _compute_line_count(self):
        for pr in self:
            pr.line_count = len(pr.line_ids)
    
    @api.depends('line_ids.teu_produced', 'line_ids.containers_produced')
    def _compute_line_totals(self):
        """Aggregate totals from production lines"""
        for pr in self:
            pr.total_teu_from_lines = sum(pr.line_ids.mapped('teu_produced'))
            pr.total_containers_from_lines = sum(pr.line_ids.mapped('containers_produced'))
    
    # ========================================================================
    # CREATE & WRITE HOOKS
    # ========================================================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-generate sequence on creation"""
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('dm.production.run') or 'New'
        
        runs = super().create(vals_list)
        
        # Phase 3A: Auto-allocate deals if passed in context
        deal_ids_to_allocate = self.env.context.get('default_deal_ids_to_allocate')
        if deal_ids_to_allocate and len(runs) == 1:
            run = runs[0]
            deals = self.env['dm.deal'].browse(deal_ids_to_allocate)
            
            # Create allocations for each deal
            for deal in deals:
                self.env['dm.allocation'].create({
                    'deal_id': deal.id,
                    'allocation_type': 'production',
                    'production_run_id': run.id,
                    'state': 'active',
                })
            
            _logger.info(
                f"Auto-allocated {len(deals)} deals to PR {run.name} from allocation board"
            )
        
        return runs
    
    # ========================================================================
    # PHASE 3: CAPACITY VALIDATION
    # ========================================================================
    
    def _check_capacity_before_confirm(self):
        """
        Phase 3: Check capacity before confirmation
        Returns: (can_confirm, warning_message)
        """
        self.ensure_one()
        
        # Check if capacity module installed
        if 'vendor_capacity_id' not in self._fields:
            return (True, '')  # No capacity module, allow confirmation
        
        if not self.supplier_id or not self.rts_date:
            return (True, '')  # No supplier/date, can't check
        
        # Trigger capacity computation
        if hasattr(self, '_compute_vendor_capacity'):
            self._compute_vendor_capacity()
        
        if hasattr(self, '_compute_capacity_status'):
            self._compute_capacity_status()
        
        # Check capacity status
        capacity_status = self.capacity_status if hasattr(self, 'capacity_status') else False
        
        if capacity_status == 'over':
            # Get details
            violations = self.capacity_violations if hasattr(self, 'capacity_violations') else ''
            return (False, violations or 'Capacity exceeded')
        
        elif capacity_status == 'warning':
            # Near capacity - allow but warn
            utilization = self.month_utilization_percent if hasattr(self, 'month_utilization_percent') else 0
            return (True, f'Near capacity limit ({utilization:.0f}% utilized)')
        
        return (True, '')
    
    def write(self, vals):
        """Override to CASCADE date changes"""
        res = super().write(vals)
        
        # CASCADE actual dates
        if 'production_start_actual' in vals:
            for pr in self:
                pr._cascade_production_start_actual()
        
        if 'rts_actual' in vals:
            for pr in self:
                pr._cascade_rts_actual()
        
        return res
    
    def action_confirm(self):
        """
        Phase 3: Enhanced confirmation with capacity check
        """
        for pr in self:
            # Check capacity
            can_confirm, message = pr._check_capacity_before_confirm()
            
            if not can_confirm:
                raise ValidationError(_(
                    "Cannot confirm production run: Capacity exceeded!\n\n%s\n\n"
                    "Please:\n"
                    "• Remove some deals from this run\n"
                    "• Split production across multiple months\n"
                    "• Increase vendor capacity\n"
                    "• Use 'Check Capacity' button for details"
                ) % message)
            
            # Show warning if near capacity
            if message:
                _logger.warning(f"PR {pr.name} confirmed with warning: {message}")
        
        self.write({'state': 'confirmed'})
        return True
    
    # ========================================================================
    # CASCADE IMPLEMENTATIONS
    # ========================================================================
    
    def _cascade_production_start_actual(self):
        """CASCADE production_start_actual to allocated deals"""
        self.ensure_one()
        
        if not self.production_start_actual:
            return
        
        for alloc in self.allocation_ids.filtered(lambda a: a.state in ['active', 'completed']):
            deal = alloc.deal_id
            if deal and not self.env.context.get('skip_cascade'):
                deal.with_context(skip_cascade=True).write({
                    'production_start_actual': self.production_start_actual
                })
                
                _logger.info(
                    f"CASCADE: PR {self.name} → Deal {deal.name}: "
                    f"production_start_actual = {self.production_start_actual}"
                )
    
    def _cascade_rts_actual(self):
        """CASCADE rts_actual to allocated deals"""
        self.ensure_one()
        
        if not self.rts_actual:
            return
        
        for alloc in self.allocation_ids.filtered(lambda a: a.state in ['active', 'completed']):
            deal = alloc.deal_id
            if deal and not self.env.context.get('skip_cascade'):
                deal.with_context(skip_cascade=True).write({
                    'rts_actual': self.rts_actual
                })
                
                _logger.info(
                    f"CASCADE: PR {self.name} → Deal {deal.name}: "
                    f"rts_actual = {self.rts_actual}"
                )
    
    # ========================================================================
    # STATE MANAGEMENT
    # ========================================================================
    
    def action_start_production(self):
        """Start production and copy ordered quantities to produced"""
        for pr in self:
            # Copy ordered → produced for all lines
            for line in pr.line_ids:
                if line.quantity_produced == 0:
                    line.write({'quantity_produced': line.quantity_ordered})
            
            # Update dates
            if not pr.production_start_actual:
                pr.write({
                    'production_start_actual': fields.Date.today(),
                    'state': 'in_production'
                })
            else:
                pr.write({'state': 'in_production'})
            
            _logger.info(f"PR {pr.name} started production with {len(pr.line_ids)} lines")
        
        return True
    
    def action_qc_pending(self):
        """
        Move to QC pending state (non-blocking documentation checkpoint).
        """
        for pr in self:
            pr.write({'state': 'qc_pending'})
            _logger.info(f"Production Run {pr.name} moved to QC pending")
        
        return True
    
    def action_mark_ready(self):
        """
        Mark production as ready to ship.
        
        This is the LOCK POINT (Phase 4B Step 3):
        1. Validates complete lots
        2. Sets rts_actual date
        3. LOCKS all line quantities (via state change)
        4. SYNCS quantity_produced to deal lines
        5. Updates deal state
        """
        for pr in self:
            # Validate state
            if pr.state != 'qc_pending':
                raise UserError(_(
                    'Production run must be in QC Pending state to mark ready.\n'
                    'Current state: %s'
                ) % dict(pr._fields['state'].selection).get(pr.state))
            
            # Validate all lines have complete lots
            incomplete_lines = pr.line_ids.filtered(
                lambda l: not l.lots_complete and l.quantity_produced > 0
            )
            
            if incomplete_lines:
                product_names = ', '.join(incomplete_lines.mapped('product_name'))
                raise ValidationError(_(
                    'Cannot set to Ready: The following products have incomplete lot details:\n%s\n\n'
                    'Please complete lot information for all produced items before proceeding.'
                ) % product_names)
            
            # Update state (this triggers quantity lock via compute)
            pr.write({
                'state': 'ready',
                'rts_actual': fields.Date.today()
            })
            
            # Sync quantities to deal lines
            pr._sync_quantities_to_deal()
            
            # Update deal states
            for alloc in pr.allocation_ids.filtered(lambda a: a.state == 'active'):
                deal = alloc.deal_id
                if hasattr(deal, '_compute_deal_state_from_allocations'):
                    deal._compute_deal_state_from_allocations()
                    _logger.info(
                        f"PR {pr.name} ready → Deal {deal.name} updated to '{deal.state}'"
                    )
            
            _logger.info(f"Production Run {pr.name} marked as ready with complete lots")
        
        return True
    
    # Add NEW method after action_mark_ready

    def _sync_quantities_to_deal(self):
        """
        Sync produced quantities from PR lines to deal lines.
        
        Called when PR is marked ready_to_ship (quantities locked).
        Uses sudo() for cross-module write permission.
        Updates both quantity_produced and production_status.
        """
        self.ensure_one()
        
        if not self.allocation_ids:
            _logger.warning(f"PR {self.name} has no allocations - skipping quantity sync")
            return
        
        synced_count = 0
        
        for pr_line in self.line_ids:
            if not pr_line.deal_line_id:
                _logger.warning(
                    f"PR line {pr_line.id} (Product: {pr_line.product_name}) "
                    f"has no deal line link - skipping quantity sync"
                )
                continue
            
            # Determine production status based on quantities
            # Must match dm_deal_line_quantities.py selection values
            if pr_line.quantity_produced <= 0:
                prod_status = 'pending'
            elif abs(pr_line.quantity_produced - pr_line.quantity_ordered) < 0.001:
                prod_status = 'completed'  # Exact match
            else:
                prod_status = 'variance'  # Any deviation (over or under)
            
            # Sync quantity_produced AND production_status to deal line
            pr_line.deal_line_id.sudo().write({
                'quantity_produced': pr_line.quantity_produced,
                'production_status': prod_status,
            })
            
            synced_count += 1
            
            _logger.debug(
                f"Synced quantity_produced={pr_line.quantity_produced}, "
                f"production_status={prod_status} "
                f"from PR line {pr_line.id} to deal line {pr_line.deal_line_id.id}"
            )
        
        # Log on PR
        self.message_post(
            body=_(
                'Production quantities synced to deal lines.<br/>'
                'Total produced: <strong>%s packages</strong> across %s lines.'
            ) % (
                sum(self.line_ids.mapped('quantity_produced')),
                synced_count
            ),
            subject=_('Quantities Locked & Synced'),
            message_type='notification'
        )
        
        # Log on each deal
        for alloc in self.allocation_ids:
            if alloc.deal_id:
                alloc.deal_id.message_post(
                    body=_(
                        'Production quantities synced from <strong>%s</strong>.<br/>'
                        'Total produced: <strong>%s packages</strong>.'
                    ) % (
                        self.name,
                        sum(self.line_ids.mapped('quantity_produced'))
                    ),
                    subject=_('Production Update'),
                    message_type='notification'
                )
        
        _logger.info(
            f"PR {self.name} synced {synced_count} quantities to deal lines"
        )
    
    def action_complete(self):
        """
        Administrative closure of production run.
        Completes allocations but maintains deal state.
        """
        for pr in self:
            pr.write({'state': 'completed'})
            
            # Complete allocations
            active_allocs = pr.allocation_ids.filtered(lambda a: a.state == 'active')
            if active_allocs:
                active_allocs.action_complete()
                _logger.info(
                    f"PR {pr.name} completed → {len(active_allocs)} allocations completed"
                )
            
            _logger.info(f"Production Run {pr.name} marked as completed")
        
        return True
    
    def action_cancel(self):
        """Cancel production run"""
        # Cancel active allocations
        self.allocation_ids.filtered(
            lambda a: a.state == 'active'
        ).action_cancel()
        self.write({'state': 'cancelled'})
        return True

    def action_reset_to_draft(self):
        """Reset to draft - emergency use only"""
        for pr in self:
            if pr.state != 'draft':
                _logger.warning(f"PR {pr.name} reset to draft from {pr.state}")
                pr.write({'state': 'draft'})
        return True

    def action_back_to_confirmed(self):
        """Move back from in_production to confirmed"""
        for pr in self:
            if pr.state == 'in_production':
                _logger.info(f"PR {pr.name} moved back to confirmed")
                pr.write({'state': 'confirmed'})
        return True

    def action_back_to_production(self):
        """Move back from qc_pending to in_production"""
        for pr in self:
            if pr.state == 'qc_pending':
                _logger.info(f"PR {pr.name} moved back to in_production")
                pr.write({'state': 'in_production'})
        return True

    def action_back_to_qc(self):
        """Move back from ready to qc_pending"""
        for pr in self:
            if pr.state == 'ready':
                _logger.info(f"PR {pr.name} moved back to qc_pending")
                pr.write({'state': 'qc_pending'})
        return True
    
    # ========================================================================
    # ACTION METHODS
    # ========================================================================
    
    def action_view_deals(self):
        """View allocated deals"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Allocated Deals'),
            'res_model': 'dm.deal',
            'view_mode': 'tree,form',
            'domain': [('id', 'in', self.deal_ids.ids)],
            'context': self.env.context,
        }
    
    def action_add_deals(self):
        """
        Phase 3A: Open wizard to add deals to this production run
        """
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Add Deals to Production'),
            'res_model': 'dm.production.allocation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_production_run_id': self.id,
                'default_create_new_pr': False,
            },
        }
    
    def action_view_lines(self):
        """View production lines"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Production Lines'),
            'res_model': 'dm.production.line',
            'view_mode': 'tree,form',
            'domain': [('production_run_id', '=', self.id)],
            'context': {'default_production_run_id': self.id},
        }
    
    # ========================================================================
    # PHASE 3A: ALLOCATION HELPERS
    # ========================================================================
    
    def check_can_allocate_deal(self, deal):
        """
        Phase 3A: Check if a deal can be allocated to this production run
        
        Args:
            deal: dm.deal record
            
        Returns:
            dict: {
                'can_allocate': bool,
                'warning': str,
                'new_total_teu': float,
                'new_utilization': float
            }
        """
        self.ensure_one()
        
        # Check supplier match
        if deal.supplier_id != self.supplier_id:
            return {
                'can_allocate': False,
                'warning': f"Supplier mismatch: Deal uses {deal.supplier_id.name}, PR uses {self.supplier_id.name}",
                'new_total_teu': 0,
                'new_utilization': 0
            }
        
        # Calculate new totals
        deal_teu = deal.total_teu if hasattr(deal, 'total_teu') else 0
        new_total_teu = self.total_teu + deal_teu
        
        # Get capacity
        capacity_teu = 0.0
        if hasattr(self, 'vendor_capacity_id') and self.vendor_capacity_id:
            capacity_teu = self.vendor_capacity_id.effective_capacity_teu
        elif self.month_capacity_teu:
            capacity_teu = self.month_capacity_teu
        
        # Check capacity if available
        if capacity_teu > 0:
            new_utilization = (new_total_teu / capacity_teu) * 100
            
            if new_utilization > 100:
                return {
                    'can_allocate': False,
                    'warning': f"Would exceed capacity: {new_utilization:.0f}% utilized ({new_total_teu:.1f} / {capacity_teu:.1f} TEU)",
                    'new_total_teu': new_total_teu,
                    'new_utilization': new_utilization
                }
            elif new_utilization > 80:
                return {
                    'can_allocate': True,
                    'warning': f"Near capacity: {new_utilization:.0f}% utilized ({new_total_teu:.1f} / {capacity_teu:.1f} TEU)",
                    'new_total_teu': new_total_teu,
                    'new_utilization': new_utilization
                }
        
        return {
            'can_allocate': True,
            'warning': '',
            'new_total_teu': new_total_teu,
            'new_utilization': new_utilization if capacity_teu > 0 else 0
        }