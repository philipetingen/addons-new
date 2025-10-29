# -*- coding: utf-8 -*-
"""
DM Capacity Planning - Production Run Extension (Phase 2)
Adds full capacity checking with month aggregation and constraint validation
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
from dateutil.relativedelta import relativedelta
import logging

_logger = logging.getLogger(__name__)


class ProductionRun(models.Model):
    _inherit = 'dm.production.run'

    # Phase 1 fields (already exist)
    vendor_capacity_id = fields.Many2one(
        'dm.vendor.capacity',
        string='Vendor Capacity',
        compute='_compute_vendor_capacity',
        store=True,
        help='The capacity record applicable for this production run'
    )
    
    capacity_status = fields.Selection([
        ('ok', 'Within Capacity'),
        ('warning', 'Near Capacity'),
        ('over', 'Over Capacity'),
        ('no_capacity', 'No Capacity Configured')
    ], string='Capacity Status', compute='_compute_capacity_status', store=True)
    
    capacity_violations = fields.Text(
        string='Capacity Violations',
        compute='_compute_capacity_status',
        help='Details of capacity violations if any'
    )

    # Phase 2 NEW fields
    month_total_teu = fields.Float(
        string='Month Total TEU',
        compute='_compute_month_capacity_usage',
        store=True,
        help='Total TEU of all production runs in the same month (same vendor)'
    )
    
    month_capacity_teu = fields.Float(
        string='Month Capacity',
        compute='_compute_month_capacity_usage',
        store=True,
        help='Vendor capacity for this month'
    )
    
    month_utilization_percent = fields.Float(
        string='Month Utilization %',
        compute='_compute_month_capacity_usage',
        store=True,
        help='Percentage of monthly capacity used'
    )
    
    month_available_teu = fields.Float(
        string='Available TEU',
        compute='_compute_month_capacity_usage',
        store=True,
        help='Remaining capacity in TEU for this month'
    )

    # Phase 3A: UI Helper Fields for Allocation Preview
    capacity_utilization_pct = fields.Float(
        string='Capacity Utilization %',
        compute='_compute_capacity_utilization_pct',
        store=True,
        digits=(16, 1),
        help='Overall capacity utilization percentage for UI display'
    )

    capacity_status_color = fields.Selection([
        ('green', 'Healthy'),
        ('yellow', 'Warning'),
        ('red', 'Over Capacity')
    ], string='Status Color',
        compute='_compute_capacity_status_color',
        store=True,
        help='Color indicator for tree view decorations'
    )

    # Helpers
    run_total_teu = fields.Float(
        string='This Run TEU',
        compute='_compute_run_total_teu',
        store=True,
        help='Total TEU for this production run only'
    )

    @api.depends('supplier_id', 'rts_date')
    def _compute_vendor_capacity(self):
        """Find the applicable capacity record for this production run"""
        capacity_model = self.env['dm.vendor.capacity']
        
        for run in self:
            if run.supplier_id and run.rts_date:
                capacity = capacity_model.get_capacity_for_date(
                    vendor_id=run.supplier_id.id,
                    target_date=run.rts_date
                )
                run.vendor_capacity_id = capacity
            else:
                run.vendor_capacity_id = False

    @api.depends('deal_ids', 'deal_ids.total_teu')
    def _compute_run_total_teu(self):
        """Calculate total TEU for this run from allocated deals"""
        for run in self:
            total = 0.0
            for deal in run.deal_ids:
                # Safe access - graceful degradation
                if hasattr(deal, 'total_teu') and deal.total_teu:
                    total += deal.total_teu
            run.run_total_teu = total

    @api.depends(
        'supplier_id', 
        'rts_date', 
        'vendor_capacity_id',
        'run_total_teu',
        'state'
    )
    def _compute_month_capacity_usage(self):
        """
        Calculate month-level capacity usage across ALL production runs
        for the same vendor in the same month
        """
        for run in self:
            if not run.supplier_id or not run.rts_date or not run.vendor_capacity_id:
                run.month_total_teu = 0.0
                run.month_capacity_teu = 0.0
                run.month_utilization_percent = 0.0
                run.month_available_teu = 0.0
                continue

            # Get month boundaries
            month_start = run.rts_date.replace(day=1)
            month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)

            # Find ALL production runs for same vendor in same month
            # Exclude cancelled runs
            domain = [
                ('supplier_id', '=', run.supplier_id.id),
                ('rts_date', '>=', month_start),
                ('rts_date', '<=', month_end),
                ('state', 'not in', ['cancelled', 'draft']),  # Only confirmed/active runs
            ]
            
            if run._origin.id:
                domain.append(('id', '!=', run._origin.id))
            
            other_runs = self.env['dm.production.run'].search(domain)
            
            # Sum TEU from all runs in month
            month_total = run.run_total_teu  # This run
            for other_run in other_runs:
                month_total += other_run.run_total_teu
            
            # Get capacity for this month
            capacity_teu = run.vendor_capacity_id.effective_capacity_teu or 0.0
            
            # Calculate utilization
            utilization = 0.0
            if capacity_teu > 0:
                utilization = (month_total / capacity_teu) * 100.0
            
            available = capacity_teu - month_total
            
            # Update fields
            run.month_total_teu = month_total
            run.month_capacity_teu = capacity_teu
            run.month_utilization_percent = utilization
            run.month_available_teu = available
            
            _logger.info(
                f"PR {run.name}: Month={month_start.strftime('%Y-%m')}, "
                f"Total={month_total:.2f} TEU, Capacity={capacity_teu:.2f} TEU, "
                f"Utilization={utilization:.1f}%"
            )

    @api.depends('month_utilization_percent')
    def _compute_capacity_utilization_pct(self):
        """
        Phase 3A: Simple wrapper around month_utilization_percent
        for UI components that need a single, clear percentage value
        """
        for run in self:
            run.capacity_utilization_pct = run.month_utilization_percent

    @api.depends('month_utilization_percent')
    def _compute_capacity_status_color(self):
        """
        Phase 3A: Determine color status based on utilization
        Green: < 80% | Yellow: 80-99% | Red: >= 100%
        """
        for run in self:
            util = run.month_utilization_percent
            
            if util >= 100:
                run.capacity_status_color = 'red'
            elif util >= 80:
                run.capacity_status_color = 'yellow'
            else:
                run.capacity_status_color = 'green'

    @api.depends(
        'vendor_capacity_id',
        'month_total_teu',
        'month_capacity_teu',
        'month_utilization_percent'
    )
    def _compute_capacity_status(self):
        """
        Enhanced capacity status with constraint checking
        Phase 2: Full implementation with detailed violations
        """
        for run in self:
            if not run.supplier_id or not run.rts_date:
                run.capacity_status = 'no_capacity'
                run.capacity_violations = 'No supplier or RTS date configured'
                continue

            if not run.vendor_capacity_id:
                run.capacity_status = 'no_capacity'
                run.capacity_violations = (
                    f'No capacity configured for vendor {run.supplier_id.name} '
                    f'on {run.rts_date.strftime("%Y-%m-%d")}'
                )
                continue

            # Run full compliance check
            result = run.check_capacity_compliance()
            
            if result['compliant']:
                run.capacity_status = 'ok'
                run.capacity_violations = False
            else:
                # Determine severity
                utilization = run.month_utilization_percent
                if utilization >= 100:
                    run.capacity_status = 'over'
                else:
                    run.capacity_status = 'warning'
                
                # Build violation message
                violations = []
                
                # Total capacity violation
                if not result['total_check']['compliant']:
                    violations.append(
                        f"❌ TOTAL CAPACITY EXCEEDED\n"
                        f"   Month: {result['total_check']['month']}\n"
                        f"   Used: {result['total_check']['used_teu']:.2f} TEU\n"
                        f"   Capacity: {result['total_check']['capacity_teu']:.2f} TEU\n"
                        f"   Over by: {result['total_check']['over_by']:.2f} TEU "
                        f"({result['total_check']['utilization']:.1f}%)"
                    )
                
                # Constraint violations
                for constraint_check in result['constraint_checks']:
                    if not constraint_check['compliant']:
                        violations.append(
                            f"⚠️ CONSTRAINT VIOLATED: {constraint_check['constraint_name']}\n"
                            f"   Products: {constraint_check['product_names']}\n"
                            f"   Used: {constraint_check['used_teu']:.2f} TEU\n"
                            f"   Limit: {constraint_check['limit_teu']:.2f} TEU\n"
                            f"   Over by: {constraint_check['over_by']:.2f} TEU "
                            f"({constraint_check['utilization']:.1f}%)"
                        )
                
                run.capacity_violations = '\n\n'.join(violations)

    def check_capacity_compliance(self):
        """
        Phase 2: Full capacity compliance checking algorithm
        
        Checks:
        1. Total month capacity (all runs combined)
        2. Individual constraint limits (product/category specific)
        
        Returns:
            dict: {
                'compliant': bool,
                'total_check': {
                    'compliant': bool,
                    'used_teu': float,
                    'capacity_teu': float,
                    'utilization': float,
                    'over_by': float,
                    'month': str
                },
                'constraint_checks': [
                    {
                        'compliant': bool,
                        'constraint_id': int,
                        'constraint_name': str,
                        'product_names': str,
                        'used_teu': float,
                        'limit_teu': float,
                        'utilization': float,
                        'over_by': float
                    },
                    ...
                ]
            }
        """
        self.ensure_one()
        
        _logger.info(f"🔍 Checking capacity compliance for PR {self.name}")
        
        # Initialize result
        result = {
            'compliant': True,
            'total_check': {},
            'constraint_checks': []
        }
        
        # Prerequisite checks
        if not self.supplier_id or not self.rts_date:
            _logger.warning(f"PR {self.name}: Missing supplier or RTS date")
            return result
        
        if not self.vendor_capacity_id:
            _logger.warning(f"PR {self.name}: No vendor capacity configured")
            return result
        
        # === STEP 1: Check Total Month Capacity ===
        
        month_str = self.rts_date.strftime('%Y-%m')
        used_teu = self.month_total_teu
        capacity_teu = self.month_capacity_teu
        
        utilization = 0.0
        if capacity_teu > 0:
            utilization = (used_teu / capacity_teu) * 100.0
        
        over_by = max(0, used_teu - capacity_teu)
        total_compliant = used_teu <= capacity_teu
        
        result['total_check'] = {
            'compliant': total_compliant,
            'used_teu': used_teu,
            'capacity_teu': capacity_teu,
            'utilization': utilization,
            'over_by': over_by,
            'month': month_str
        }
        
        if not total_compliant:
            result['compliant'] = False
            _logger.warning(
                f"PR {self.name}: Total capacity exceeded - "
                f"{used_teu:.2f}/{capacity_teu:.2f} TEU ({utilization:.1f}%)"
            )
        
        # === STEP 2: Check Individual Constraints ===
        
        constraints = self.vendor_capacity_id.constraint_ids.filtered(lambda c: c.active)
        
        if not constraints:
            _logger.info(f"PR {self.name}: No constraints to check")
            return result
        
        # Get all deals from all runs in the same month
        month_start = self.rts_date.replace(day=1)
        month_end = (month_start + relativedelta(months=1)) - relativedelta(days=1)
        
        all_runs = self.env['dm.production.run'].search([
            ('supplier_id', '=', self.supplier_id.id),
            ('rts_date', '>=', month_start),
            ('rts_date', '<=', month_end),
            ('state', 'not in', ['cancelled', 'draft'])
        ])
        
        all_deals = all_runs.mapped('deal_ids')
        
        _logger.info(f"PR {self.name}: Checking {len(constraints)} constraints against {len(all_deals)} deals")
        
        for constraint in constraints:
            constraint_check = self._check_single_constraint(constraint, all_deals)
            result['constraint_checks'].append(constraint_check)
            
            if not constraint_check['compliant']:
                result['compliant'] = False
                _logger.warning(
                    f"PR {self.name}: Constraint violated - {constraint.name} - "
                    f"{constraint_check['used_teu']:.2f}/{constraint_check['limit_teu']:.2f} TEU"
                )
        
        _logger.info(f"PR {self.name}: Compliance check complete - Compliant: {result['compliant']}")
        
        return result

    def _check_single_constraint(self, constraint, deals):
        """
        Check a single constraint against a set of deals
        
        Args:
            constraint: dm.vendor.capacity.constraint record
            deals: recordset of dm.deal records
            
        Returns:
            dict: Constraint check result
        """
        # Get constrained products
        constrained_products = constraint.get_constrained_products()
        
        # Filter deals that match this constraint
        matching_teu = 0.0
        
        for deal in deals:
            # Check if deal has any products matching this constraint
            deal_products = deal.product_id  # Assuming deal has product_id
            
            if not deal_products:
                continue
            
            # Check if product matches constraint
            if constraint.check_product_matches(deal_products):
                # Add this deal's TEU to the constraint total
                if hasattr(deal, 'total_teu') and deal.total_teu:
                    matching_teu += deal.total_teu
        
        # Compare against constraint limit
        limit_teu = constraint.effective_max_capacity_teu or 0.0
        utilization = 0.0
        if limit_teu > 0:
            utilization = (matching_teu / limit_teu) * 100.0
        
        over_by = max(0, matching_teu - limit_teu)
        compliant = matching_teu <= limit_teu
        
        # Get product names for display
        product_names = ', '.join(constrained_products.mapped('name')[:5])  # First 5
        if len(constrained_products) > 5:
            product_names += f' (+{len(constrained_products) - 5} more)'
        
        return {
            'compliant': compliant,
            'constraint_id': constraint.id,
            'constraint_name': constraint.name,
            'product_names': product_names,
            'used_teu': matching_teu,
            'limit_teu': limit_teu,
            'utilization': utilization,
            'over_by': over_by
        }

    def check_can_allocate_deal(self, deal):
        """
        Phase 3A: Check if a deal can be allocated to this production run
        WITHOUT creating the allocation.
        
        Used by: Quick Allocate Wizard for capacity preview
        
        Args:
            deal: dm.deal record to potentially allocate
            
        Returns:
            dict: {
                'can_allocate': bool - True if within limits (may have warnings)
                'warning': str or False - Warning message if near/over capacity
                'new_total_teu': float - Total TEU after allocation
                'new_utilization': float - Utilization % after allocation
                'capacity_status_color': str - 'green'/'yellow'/'red'
            }
        """
        self.ensure_one()
        
        result = {
            'can_allocate': True,
            'warning': False,
            'new_total_teu': 0.0,
            'new_utilization': 0.0,
            'capacity_status_color': 'green'
        }
        
        # Get deal TEU (with graceful degradation)
        deal_teu = 0.0
        if hasattr(deal, 'total_teu') and deal.total_teu:
            deal_teu = deal.total_teu
        
        if deal_teu == 0:
            result['warning'] = "Deal has no TEU calculated"
            return result
        
        # Check if we have capacity configured
        if not self.vendor_capacity_id:
            result['warning'] = "No capacity configured for this vendor"
            return result
        
        # Calculate new totals
        current_month_teu = self.month_total_teu or 0.0
        capacity_teu = self.month_capacity_teu or 0.0
        
        result['new_total_teu'] = current_month_teu + deal_teu
        
        if capacity_teu > 0:
            result['new_utilization'] = (result['new_total_teu'] / capacity_teu) * 100.0
        else:
            result['new_utilization'] = 0.0
        
        # Determine status color and warnings
        if result['new_utilization'] >= 100:
            result['capacity_status_color'] = 'red'
            result['warning'] = (
                f"Over capacity! Adding this deal would use "
                f"{result['new_utilization']:.1f}% of monthly capacity "
                f"({result['new_total_teu']:.1f} / {capacity_teu:.1f} TEU)"
            )
            result['can_allocate'] = True  # Allow but warn
            
        elif result['new_utilization'] >= 80:
            result['capacity_status_color'] = 'yellow'
            result['warning'] = (
                f"Near capacity! Adding this deal would use "
                f"{result['new_utilization']:.1f}% of monthly capacity "
                f"({result['new_total_teu']:.1f} / {capacity_teu:.1f} TEU)"
            )
            result['can_allocate'] = True
            
        else:
            result['capacity_status_color'] = 'green'
            result['can_allocate'] = True
        
        _logger.info(
            f"PR {self.name}: Can allocate deal {deal.name}? "
            f"New utilization: {result['new_utilization']:.1f}%"
        )
        
        return result

    def action_check_capacity(self):
        """
        Phase 2: Enhanced wizard with visual feedback
        Open capacity check wizard showing detailed analysis
        """
        self.ensure_one()
        
        # Run compliance check
        result = self.check_capacity_compliance()
        
        # Return wizard action
        return {
            'name': _('Capacity Check Results'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.capacity.check.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_production_run_id': self.id,
                'default_check_result': result,
            }
        }