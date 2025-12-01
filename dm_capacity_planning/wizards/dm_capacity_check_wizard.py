# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from dateutil.relativedelta import relativedelta
from datetime import date
from collections import defaultdict
import logging

_logger = logging.getLogger(__name__)


class DmCapacityCheckWizard(models.TransientModel):
    """
    Capacity Compliance Check Wizard
    
    Validates capacity compliance for a vendor and date range.
    Can be called standalone or integrated into deal workflows.
    """
    _name = 'dm.capacity.check.wizard'
    _description = 'Capacity Check Wizard'
    
    # =========================================================================
    # INPUT PARAMETERS
    # =========================================================================
    
    vendor_id = fields.Many2one(
        'res.partner',
        string='Vendor',
        required=True,
        domain=[('supplier_rank', '>', 0)],
        help='Vendor to check capacity for'
    )
    
    date_from = fields.Date(
        string='Check From',
        required=True,
        default=fields.Date.today,
        help='Start date for capacity check'
    )
    
    date_to = fields.Date(
        string='Check To',
        required=True,
        default=lambda self: fields.Date.today() + relativedelta(months=3),
        help='End date for capacity check'
    )
    
    # =========================================================================
    # CHECK RESULTS
    # =========================================================================
    
    state = fields.Selection([
        ('input', 'Input Parameters'),
        ('result', 'Check Results'),
    ], default='input', string='State')
    
    check_passed = fields.Boolean(
        string='Check Passed',
        readonly=True,
        help='True if all capacity checks passed'
    )
    
    result_message = fields.Html(
        string='Results',
        readonly=True,
        help='Detailed capacity check results'
    )
    
    violation_count = fields.Integer(
        string='Violations',
        readonly=True,
        help='Number of capacity violations found'
    )
    
    # =========================================================================
    # PROGRESS TRACKING
    # =========================================================================
    
    progress_message = fields.Char(
        string='Progress',
        readonly=True
    )
    
    progress_percent = fields.Float(
        string='Progress %',
        readonly=True
    )
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    @api.constrains('date_from', 'date_to')
    def _check_date_range(self):
        """Validate date range"""
        for wizard in self:
            if wizard.date_to < wizard.date_from:
                raise ValidationError(_("End date must be after start date."))
    
    # =========================================================================
    # CAPACITY CHECK ALGORITHM
    # =========================================================================
    
    def action_check_capacity(self):
        """
        Execute capacity compliance check
        
        Algorithm:
        1. Get all capacity records for vendor in date range
        2. Aggregate committed capacity by month
        3. Check total capacity limits
        4. Check constraint-specific limits
        5. Report violations
        """
        self.ensure_one()
        
        _logger.info(f"Starting capacity check for vendor {self.vendor_id.name} "
                    f"from {self.date_from} to {self.date_to}")
        
        # Update progress
        self.write({
            'state': 'result',
            'progress_message': 'Analyzing capacity records...',
            'progress_percent': 10.0
        })
        
        # Get capacity records for vendor in date range
        capacity_records = self._get_capacity_records()
        
        if not capacity_records:
            self.write({
                'check_passed': True,
                'result_message': self._format_no_capacity_message(),
                'violation_count': 0,
                'progress_percent': 100.0,
                'progress_message': 'Complete'
            })
            return self._return_wizard_action()
        
        # Update progress
        self.write({
            'progress_message': 'Calculating monthly allocations...',
            'progress_percent': 30.0
        })
        
        # Get committed capacity (from deals requesting production)
        monthly_commitments = self._get_monthly_commitments()
        
        # Update progress
        self.write({
            'progress_message': 'Checking capacity limits...',
            'progress_percent': 60.0
        })
        
        # Check capacity compliance
        violations = self._check_capacity_compliance(
            capacity_records, 
            monthly_commitments
        )
        
        # Update progress
        self.write({
            'progress_message': 'Generating report...',
            'progress_percent': 90.0
        })
        
        # Format results
        result_html = self._format_results(
            capacity_records,
            monthly_commitments,
            violations
        )
        
        # Final update
        self.write({
            'check_passed': len(violations) == 0,
            'result_message': result_html,
            'violation_count': len(violations),
            'progress_percent': 100.0,
            'progress_message': 'Complete'
        })
        
        _logger.info(f"Capacity check complete: {len(violations)} violations found")
        
        return self._return_wizard_action()
    
    def _get_capacity_records(self):
        """Get capacity records overlapping with check period"""
        return self.env['dm.vendor.capacity'].search([
            ('vendor_id', '=', self.vendor_id.id),
            ('active', '=', True),
            '|',
            '&',
            ('valid_from', '<=', self.date_to),
            '|',
            ('valid_to', '=', False),
            ('valid_to', '>=', self.date_from),
            '&',
            ('valid_from', '<=', self.date_from),
            ('valid_to', '=', False),
        ])
    
    def _get_monthly_commitments(self):
        """
        Get monthly committed capacity from deals
        
        Returns:
            dict: {
                'YYYY-MM': {
                    'total_teu': float,
                    'by_product': {product_id: teu_amount, ...}
                }
            }
        """
        # TODO Sprint 5: Query dm.deal records requesting production
        # For now, return empty commitments
        return {}
    
    def _check_capacity_compliance(self, capacity_records, monthly_commitments):
        """
        Check if commitments exceed capacity limits
        
        Returns:
            list: [{'month': 'YYYY-MM', 'type': 'total|constraint', 'message': '...'}]
        """
        violations = []
        
        # For each month in range
        current = self.date_from.replace(day=1)
        end = self.date_to.replace(day=1)
        
        while current <= end:
            month_key = current.strftime('%Y-%m')
            
            # Get active capacity for this month
            active_capacity = self._get_active_capacity_for_month(
                capacity_records, 
                current
            )
            
            if not active_capacity:
                current = current + relativedelta(months=1)
                continue
            
            # Get commitments for this month
            commitments = monthly_commitments.get(month_key, {})
            total_committed = commitments.get('total_teu', 0.0)
            
            # Check total capacity
            if total_committed > active_capacity.effective_capacity_teu:
                violations.append({
                    'month': month_key,
                    'type': 'total',
                    'message': f"Total capacity exceeded: {total_committed:.2f} TEU committed "
                              f"vs {active_capacity.effective_capacity_teu:.2f} TEU available"
                })
            
            # Check constraint-specific limits
            for constraint in active_capacity.constraint_ids.filtered('active'):
                constraint_committed = self._calculate_constraint_committed(
                    constraint,
                    commitments.get('by_product', {})
                )
                
                if constraint_committed > constraint.effective_max_capacity_teu:
                    violations.append({
                        'month': month_key,
                        'type': 'constraint',
                        'constraint_name': constraint.name,
                        'message': f"Constraint '{constraint.name}' exceeded: "
                                  f"{constraint_committed:.2f} TEU committed "
                                  f"vs {constraint.effective_max_capacity_teu:.2f} TEU limit"
                    })
            
            current = current + relativedelta(months=1)
        
        return violations
    
    def _get_active_capacity_for_month(self, capacity_records, month_date):
        """Get capacity record active for given month"""
        for capacity in capacity_records:
            if capacity.valid_from <= month_date:
                if not capacity.valid_to or capacity.valid_to >= month_date:
                    return capacity
        return False
    
    def _calculate_constraint_committed(self, constraint, product_commitments):
        """Calculate committed TEU for products matching constraint"""
        total = 0.0
        
        constrained_products = constraint.get_constrained_products()
        
        for product_id, teu_amount in product_commitments.items():
            product = self.env['product.product'].browse(product_id)
            if product in constrained_products:
                total += teu_amount
        
        return total
    
    # =========================================================================
    # RESULT FORMATTING
    # =========================================================================
    
    def _format_results(self, capacity_records, commitments, violations):
        """Format check results as HTML"""
        html = ['<div style="font-family: Arial, sans-serif;">']
        
        # Summary header
        if violations:
            html.append(
                f'<h3 style="color: #d9534f;">⚠️ Capacity Check Failed</h3>'
                f'<p><strong>{len(violations)} violation(s) found</strong></p>'
            )
        else:
            html.append(
                f'<h3 style="color: #5cb85c;">✓ Capacity Check Passed</h3>'
                f'<p>All capacity limits respected in the checked period.</p>'
            )
        
        # Violations detail
        if violations:
            html.append('<h4>Violations:</h4><ul>')
            for v in violations:
                html.append(f'<li><strong>{v["month"]}:</strong> {v["message"]}</li>')
            html.append('</ul>')
        
        # Capacity summary
        html.append('<h4>Capacity Configuration:</h4><ul>')
        for capacity in capacity_records:
            period = f"{capacity.valid_from} to {capacity.valid_to or 'Present'}"
            html.append(
                f'<li>{period}: <strong>{capacity.effective_capacity_teu:.2f} TEU/month</strong>'
            )
            if capacity.constraint_ids:
                html.append('<ul>')
                for constraint in capacity.constraint_ids.filtered('active'):
                    html.append(
                        f'<li>{constraint.name}: '
                        f'{constraint.effective_max_capacity_teu:.2f} TEU/month</li>'
                    )
                html.append('</ul>')
            html.append('</li>')
        html.append('</ul>')
        
        html.append('</div>')
        
        return ''.join(html)
    
    def _format_no_capacity_message(self):
        """Format message when no capacity configured"""
        return f"""
        <div style="font-family: Arial, sans-serif;">
            <h3 style="color: #f0ad4e;">⚠️ No Capacity Configured</h3>
            <p>Vendor <strong>{self.vendor_id.name}</strong> has no capacity records 
            for the period {self.date_from} to {self.date_to}.</p>
            <p>Please configure capacity before allocating production.</p>
        </div>
        """
    
    def _return_wizard_action(self):
        """Return action to keep wizard open"""
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    # =========================================================================
    # ACTIONS
    # =========================================================================
    
    def action_close(self):
        """Close wizard"""
        return {'type': 'ir.actions.act_window_close'}
    
    def action_reset(self):
        """Reset to input state"""
        self.write({
            'state': 'input',
            'check_passed': False,
            'result_message': False,
            'violation_count': 0,
            'progress_message': False,
            'progress_percent': 0.0,
        })
        return self._return_wizard_action()