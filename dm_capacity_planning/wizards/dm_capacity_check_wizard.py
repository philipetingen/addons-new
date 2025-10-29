# -*- coding: utf-8 -*-
"""
DM Capacity Planning - Capacity Check Wizard (Phase 2)
Visual capacity checking with progress bars and detailed violation reports
"""

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class CapacityCheckWizard(models.TransientModel):
    _name = 'dm.capacity.check.wizard'
    _description = 'Capacity Check Results'

    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        required=True,
        readonly=True
    )
    
    # Display fields
    vendor_name = fields.Char(
        string='Vendor',
        related='production_run_id.supplier_id.name',
        readonly=True
    )
    
    rts_date = fields.Date(
        string='RTS Date',
        related='production_run_id.rts_date',
        readonly=True
    )
    
    month_display = fields.Char(
        string='Month',
        compute='_compute_month_display',
        readonly=True
    )
    
    # Overall status
    overall_status = fields.Selection([
        ('ok', 'Within Capacity'),
        ('warning', 'Near Capacity'),
        ('over', 'Over Capacity')
    ], string='Overall Status', compute='_compute_overall_status')
    
    overall_compliant = fields.Boolean(
        string='Compliant',
        compute='_compute_overall_status'
    )
    
    # Total capacity metrics
    this_run_teu = fields.Float(
        string='This Run TEU',
        related='production_run_id.run_total_teu',
        readonly=True
    )
    
    month_total_teu = fields.Float(
        string='Month Total TEU',
        related='production_run_id.month_total_teu',
        readonly=True
    )
    
    month_capacity_teu = fields.Float(
        string='Month Capacity',
        related='production_run_id.month_capacity_teu',
        readonly=True
    )
    
    month_utilization_percent = fields.Float(
        string='Utilization %',
        related='production_run_id.month_utilization_percent',
        readonly=True
    )
    
    month_available_teu = fields.Float(
        string='Available TEU',
        related='production_run_id.month_available_teu',
        readonly=True
    )
    
    # Detailed results (stored as JSON)
    check_result_json = fields.Text(
        string='Check Result JSON',
        help='Detailed check results in JSON format'
    )
    
    # HTML rendering
    result_html = fields.Html(
        string='Results',
        compute='_compute_result_html',
        sanitize=False
    )
    
    # Constraint checks
    constraint_check_ids = fields.One2many(
        'dm.capacity.check.constraint',
        'wizard_id',
        string='Constraint Checks'
    )

    @api.depends('rts_date')
    def _compute_month_display(self):
        for wizard in self:
            if wizard.rts_date:
                wizard.month_display = wizard.rts_date.strftime('%B %Y')
            else:
                wizard.month_display = ''

    @api.depends(
        'month_total_teu',
        'month_capacity_teu',
        'constraint_check_ids.compliant'
    )
    def _compute_overall_status(self):
        for wizard in self:
            # Check if any constraints violated
            constraint_violation = any(
                not check.compliant 
                for check in wizard.constraint_check_ids
            )
            
            # Check total capacity
            utilization = wizard.month_utilization_percent
            capacity_ok = utilization <= 100
            
            # Determine overall status
            if capacity_ok and not constraint_violation:
                wizard.overall_status = 'ok'
                wizard.overall_compliant = True
            elif utilization >= 100 or constraint_violation:
                wizard.overall_status = 'over'
                wizard.overall_compliant = False
            else:
                # Near capacity (80-100%)
                wizard.overall_status = 'warning'
                wizard.overall_compliant = True

    @api.depends(
        'month_total_teu',
        'month_capacity_teu',
        'month_utilization_percent',
        'constraint_check_ids',
        'overall_status'
    )
    def _compute_result_html(self):
        """Generate visual HTML report with progress bars"""
        for wizard in self:
            html_parts = []
            
            # Header with overall status
            status_icon = {
                'ok': '✅',
                'warning': '⚠️',
                'over': '❌'
            }.get(wizard.overall_status, '❓')
            
            status_color = {
                'ok': '#28a745',
                'warning': '#ffc107',
                'over': '#dc3545'
            }.get(wizard.overall_status, '#6c757d')
            
            status_text = {
                'ok': 'Within Capacity',
                'warning': 'Near Capacity Limit',
                'over': 'CAPACITY EXCEEDED'
            }.get(wizard.overall_status, 'Unknown')
            
            html_parts.append(f"""
            <div style="padding: 20px; background: #f8f9fa; border-radius: 8px; margin-bottom: 20px;">
                <h2 style="margin: 0 0 10px 0; color: {status_color};">
                    {status_icon} {status_text}
                </h2>
                <p style="margin: 0; color: #6c757d; font-size: 14px;">
                    Capacity analysis for <strong>{wizard.vendor_name}</strong> 
                    in <strong>{wizard.month_display}</strong>
                </p>
            </div>
            """)
            
            # === Total Capacity Section ===
            utilization = wizard.month_utilization_percent
            progress_color = '#28a745'  # Green
            if utilization >= 100:
                progress_color = '#dc3545'  # Red
            elif utilization >= 80:
                progress_color = '#ffc107'  # Yellow
            
            progress_width = min(utilization, 100)  # Cap at 100% visual
            
            html_parts.append(f"""
            <div style="margin-bottom: 30px;">
                <h3 style="margin: 0 0 15px 0; font-size: 18px;">
                    📦 Total Month Capacity
                </h3>
                
                <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                        <span style="font-weight: bold;">Usage: {wizard.month_total_teu:.2f} / {wizard.month_capacity_teu:.2f} TEU</span>
                        <span style="font-weight: bold; color: {progress_color};">{utilization:.1f}%</span>
                    </div>
                    
                    <div style="background: #e9ecef; height: 30px; border-radius: 15px; overflow: hidden; position: relative;">
                        <div style="background: {progress_color}; height: 100%; width: {progress_width}%; transition: width 0.3s;"></div>
                        {f'<div style="position: absolute; top: 0; left: 0; right: 0; bottom: 0; display: flex; align-items: center; justify-content: center; color: white; font-weight: bold; text-shadow: 1px 1px 2px rgba(0,0,0,0.5);">{utilization:.1f}%</div>' if progress_width > 20 else ''}
                    </div>
                    
                    <div style="margin-top: 15px; display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;">
                        <div style="text-align: center; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                            <div style="font-size: 12px; color: #6c757d; margin-bottom: 5px;">This Run</div>
                            <div style="font-size: 18px; font-weight: bold; color: #007bff;">{wizard.this_run_teu:.2f} TEU</div>
                        </div>
                        <div style="text-align: center; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                            <div style="font-size: 12px; color: #6c757d; margin-bottom: 5px;">Month Total</div>
                            <div style="font-size: 18px; font-weight: bold;">{wizard.month_total_teu:.2f} TEU</div>
                        </div>
                        <div style="text-align: center; padding: 10px; background: #f8f9fa; border-radius: 5px;">
                            <div style="font-size: 12px; color: #6c757d; margin-bottom: 5px;">Available</div>
                            <div style="font-size: 18px; font-weight: bold; color: {'#28a745' if wizard.month_available_teu >= 0 else '#dc3545'};">
                                {wizard.month_available_teu:.2f} TEU
                            </div>
                        </div>
                    </div>
                </div>
            </div>
            """)
            
            # === Constraint Checks Section ===
            if wizard.constraint_check_ids:
                html_parts.append(f"""
                <div style="margin-bottom: 30px;">
                    <h3 style="margin: 0 0 15px 0; font-size: 18px;">
                        🎯 Product/Category Constraints
                    </h3>
                """)
                
                for constraint_check in wizard.constraint_check_ids:
                    c_utilization = constraint_check.utilization_percent
                    c_color = '#28a745'  # Green
                    c_icon = '✅'
                    
                    if c_utilization >= 100:
                        c_color = '#dc3545'  # Red
                        c_icon = '❌'
                    elif c_utilization >= 80:
                        c_color = '#ffc107'  # Yellow
                        c_icon = '⚠️'
                    
                    c_width = min(c_utilization, 100)
                    
                    html_parts.append(f"""
                    <div style="background: white; padding: 15px; border-radius: 8px; border: 1px solid #dee2e6; margin-bottom: 15px;">
                        <div style="display: flex; align-items: center; margin-bottom: 10px;">
                            <span style="font-size: 20px; margin-right: 10px;">{c_icon}</span>
                            <div style="flex: 1;">
                                <div style="font-weight: bold; margin-bottom: 5px;">{constraint_check.constraint_name}</div>
                                <div style="font-size: 12px; color: #6c757d;">{constraint_check.product_names}</div>
                            </div>
                        </div>
                        
                        <div style="display: flex; justify-content: space-between; margin-bottom: 10px;">
                            <span>Usage: {constraint_check.used_teu:.2f} / {constraint_check.limit_teu:.2f} TEU</span>
                            <span style="font-weight: bold; color: {c_color};">{c_utilization:.1f}%</span>
                        </div>
                        
                        <div style="background: #e9ecef; height: 20px; border-radius: 10px; overflow: hidden; position: relative;">
                            <div style="background: {c_color}; height: 100%; width: {c_width}%; transition: width 0.3s;"></div>
                        </div>
                        
                        {f'<div style="margin-top: 10px; padding: 10px; background: #fff3cd; border-left: 3px solid #ffc107; border-radius: 3px; font-size: 13px;"><strong>⚠️ Warning:</strong> Over limit by {constraint_check.over_by:.2f} TEU</div>' if constraint_check.over_by > 0 else ''}
                    </div>
                    """)
                
                html_parts.append("</div>")
            else:
                html_parts.append(f"""
                <div style="padding: 15px; background: #e7f3ff; border-radius: 8px; border-left: 3px solid #007bff;">
                    <strong>ℹ️ Info:</strong> No product/category constraints configured for this capacity.
                </div>
                """)
            
            # === Summary/Actions ===
            if wizard.overall_status == 'over':
                html_parts.append(f"""
                <div style="padding: 15px; background: #f8d7da; border-radius: 8px; border-left: 3px solid #dc3545; margin-top: 20px;">
                    <strong>❌ Action Required:</strong> Capacity exceeded! Consider:
                    <ul style="margin: 10px 0 0 20px;">
                        <li>Splitting production across multiple months</li>
                        <li>Allocating to a different vendor</li>
                        <li>Increasing vendor capacity for this period</li>
                    </ul>
                </div>
                """)
            elif wizard.overall_status == 'warning':
                html_parts.append(f"""
                <div style="padding: 15px; background: #fff3cd; border-radius: 8px; border-left: 3px solid #ffc107; margin-top: 20px;">
                    <strong>⚠️ Warning:</strong> Near capacity limit. Monitor additional allocations carefully.
                </div>
                """)
            else:
                html_parts.append(f"""
                <div style="padding: 15px; background: #d4edda; border-radius: 8px; border-left: 3px solid #28a745; margin-top: 20px;">
                    <strong>✅ All Clear:</strong> Within capacity limits. {wizard.month_available_teu:.2f} TEU still available this month.
                </div>
                """)
            
            wizard.result_html = ''.join(html_parts)

    @api.model
    def default_get(self, fields_list):
        """Populate wizard from context"""
        res = super().default_get(fields_list)
        
        if 'default_check_result' in self.env.context:
            check_result = self.env.context['default_check_result']
            res['check_result_json'] = json.dumps(check_result)
        
        return res

    @api.model
    def create(self, vals):
        """Create wizard and populate constraint checks"""
        wizard = super().create(vals)
        
        # Parse check result and create constraint check lines
        if wizard.check_result_json:
            try:
                result = json.loads(wizard.check_result_json)
                
                for constraint_check in result.get('constraint_checks', []):
                    self.env['dm.capacity.check.constraint'].create({
                        'wizard_id': wizard.id,
                        'constraint_id': constraint_check['constraint_id'],
                        'constraint_name': constraint_check['constraint_name'],
                        'product_names': constraint_check['product_names'],
                        'used_teu': constraint_check['used_teu'],
                        'limit_teu': constraint_check['limit_teu'],
                        'utilization_percent': constraint_check['utilization'],
                        'over_by': constraint_check['over_by'],
                        'compliant': constraint_check['compliant']
                    })
                    
            except Exception as e:
                _logger.error(f"Error parsing check result: {e}")
        
        return wizard

    def action_close(self):
        """Close the wizard"""
        return {'type': 'ir.actions.act_window_close'}

    def action_view_capacity_record(self):
        """Open the vendor capacity record"""
        self.ensure_one()
        
        if not self.production_run_id.vendor_capacity_id:
            raise UserError(_('No capacity record found for this production run'))
        
        return {
            'name': _('Vendor Capacity'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.vendor.capacity',
            'res_id': self.production_run_id.vendor_capacity_id.id,
            'view_mode': 'form',
            'target': 'current'
        }


class CapacityCheckConstraint(models.TransientModel):
    """Individual constraint check result line"""
    
    _name = 'dm.capacity.check.constraint'
    _description = 'Capacity Check Constraint Result'
    _order = 'utilization_percent desc'

    wizard_id = fields.Many2one(
        'dm.capacity.check.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    constraint_id = fields.Many2one(
        'dm.vendor.capacity.constraint',
        string='Constraint',
        readonly=True
    )
    
    constraint_name = fields.Char(
        string='Constraint',
        readonly=True
    )
    
    product_names = fields.Text(
        string='Products/Categories',
        readonly=True
    )
    
    used_teu = fields.Float(
        string='Used TEU',
        readonly=True,
        digits=(10, 2)
    )
    
    limit_teu = fields.Float(
        string='Limit TEU',
        readonly=True,
        digits=(10, 2)
    )
    
    utilization_percent = fields.Float(
        string='Utilization %',
        readonly=True,
        digits=(5, 1)
    )
    
    over_by = fields.Float(
        string='Over By',
        readonly=True,
        digits=(10, 2)
    )
    
    compliant = fields.Boolean(
        string='Compliant',
        readonly=True
    )
    
    status_icon = fields.Char(
        string='Status',
        compute='_compute_status_icon'
    )

    @api.depends('compliant', 'utilization_percent')
    def _compute_status_icon(self):
        for check in self:
            if check.utilization_percent >= 100:
                check.status_icon = '❌'
            elif check.utilization_percent >= 80:
                check.status_icon = '⚠️'
            else:
                check.status_icon = '✅'