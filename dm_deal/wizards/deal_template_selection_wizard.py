# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DealTemplateSelectionWizard(models.TransientModel):
    """
    Wizard for selecting from multiple matching deal templates.
    
    NO deal_id required - works with unsaved deals!
    Returns selected template back to calling context.
    """
    _name = 'dm.deal.template.selection.wizard'
    _description = 'Deal Template Selection Wizard'
    
    # NO deal_id field - we don't need it!
    
    template_ids = fields.Many2many(
        'dm.deal.template',
        string='Matching Templates',
        required=True,
        readonly=True,
        help='All templates that match this deal'
    )
    
    selected_template_id = fields.Many2one(
        'dm.deal.template',
        string='Selected Template',
        domain="[('id', 'in', template_ids)]",
        help='Choose the template to apply to this deal'
    )
    
    comparison_html = fields.Html(
        string='Template Comparison',
        compute='_compute_comparison_html',
        sanitize=False
    )
    
    template_count = fields.Integer(
        string='Number of Templates',
        compute='_compute_template_count'
    )

    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        readonly=True
    )

    def _open_template_selection_wizard(self, templates):
        """Open wizard for template selection"""
        
        wizard_vals = {
            'template_ids': [(6, 0, templates.ids)],
        }
        
        # Only set deal_id if deal is saved (has real ID)
        if self.id and not isinstance(self.id, models.NewId):
            wizard_vals['deal_id'] = self.id
        
        wizard = self.env['dm.deal.template.selection.wizard'].create(wizard_vals)
        
        return {
            'name': _('Select Deal Template'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.template.selection.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }
    
    @api.depends('template_ids')
    def _compute_template_count(self):
        for wizard in self:
            wizard.template_count = len(wizard.template_ids)
    
    @api.depends('template_ids')
    def _compute_comparison_html(self):
        """Build HTML comparison table showing template differences"""
        for wizard in self:
            if not wizard.template_ids:
                wizard.comparison_html = '<p>No templates to compare.</p>'
                continue
            
            # Helper function to get field display value
            def get_display_value(template, field_name):
                value = getattr(template, field_name, None)
                if not value:
                    return '<em style="color: #999;">Not set</em>'
                
                if hasattr(value, 'name'):
                    return value.name
                
                if isinstance(value, bool):
                    return '✓ Yes' if value else '✗ No'
                
                if isinstance(value, (int, float)):
                    return str(value)
                
                return str(value)
            
            # Build comparison table
            html = '''
                <style>
                    .template-comparison {
                        width: 100%;
                        border-collapse: collapse;
                        font-size: 13px;
                    }
                    .template-comparison th {
                        background-color: #875A7B;
                        color: white;
                        padding: 10px;
                        text-align: left;
                        font-weight: bold;
                    }
                    .template-comparison td {
                        padding: 8px;
                        border: 1px solid #ddd;
                    }
                    .template-comparison tr:nth-child(even) {
                        background-color: #f9f9f9;
                    }
                    .template-comparison tr:hover {
                        background-color: #f5f5f5;
                    }
                    .field-label {
                        font-weight: bold;
                        color: #666;
                    }
                </style>
                <table class="template-comparison">
                    <thead>
                        <tr>
                            <th>Field</th>
            '''
            
            for template in wizard.template_ids:
                html += f'<th>{template.name}</th>'
            
            html += '</tr></thead><tbody>'
            
            # Define fields to compare
            comparison_fields = [
                ('Template Type', 'template_type'),
                ('Supplier', 'supplier_id'),  # ← ADDED
                ('Priority', 'priority'),
                ('', ''),  # Separator
                ('<strong>Sales Terms</strong>', ''),
                ('Sales Payment Terms', 'sale_payment_term_id'),
                ('Sales Incoterm', 'sale_incoterm_id'),
                ('Sales Incoterm Location', 'sale_incoterm_location'),
                ('', ''),  # Separator
                ('<strong>Purchase Terms</strong>', ''),
                ('Purchase Payment Terms', 'purchase_payment_term_id'),
                ('Purchase Incoterm', 'purchase_incoterm_id'),
                ('Purchase Incoterm Location', 'purchase_incoterm_location'),
                ('', ''),  # Separator
                ('<strong>Logistics</strong>', ''),
                ('Port of Loading', 'loading_port_id'),
                ('Port of Discharge', 'discharge_port_id'),
                ('', ''),  # Separator
                ('<strong>Lead Times</strong>', ''),
                ('Total Lead Time (days)', 'total_lead_time'),
                ('Production Lead Time (days)', 'production_lead_time'),
                ('Transit Lead Time (days)', 'transit_lead_time'),
                ('', ''),  # Separator
                ('<strong>Invoice Settings</strong>', ''),
                ('Split Invoice', 'invoice_split'),
                ('Product Invoice %', 'product_invoice_percentage'),
            ]
            
            for label, field_name in comparison_fields:
                if not field_name:
                    if label:
                        html += f'<tr><td colspan="{len(wizard.template_ids) + 1}" class="field-label">{label}</td></tr>'
                    else:
                        html += f'<tr><td colspan="{len(wizard.template_ids) + 1}" style="height: 5px; background: #eee;"></td></tr>'
                    continue
                
                html += f'<tr><td class="field-label">{label}</td>'
                
                for template in wizard.template_ids:
                    value_html = get_display_value(template, field_name)
                    html += f'<td>{value_html}</td>'
                
                html += '</tr>'
            
            html += '</tbody></table>'
            
            html += f'''
                <div style="margin-top: 15px; padding: 10px; background: #f0f8ff; border-left: 4px solid #875A7B;">
                    <strong>ℹ️ Selection Help:</strong>
                    <ul style="margin: 5px 0 0 20px;">
                        <li>Compare the templates above and select the one that best matches your requirements</li>
                        <li>Pay special attention to ports, payment terms, and lead times</li>
                        <li>You can skip selection and manually configure the deal if needed</li>
                    </ul>
                </div>
            '''
            
            wizard.comparison_html = html
    
    def action_apply_selected(self):
            """Apply selected template - delegates to model"""
            self.ensure_one()
            
            if not self.selected_template_id:
                raise UserError(_('Please select a template to apply.'))
            
            # Apply to deal if deal_id exists
            if self.deal_id:
                self.deal_id.apply_selected_template_from_wizard(self.selected_template_id.id)
                _logger.info(f"Template '{self.selected_template_id.name}' applied to deal {self.deal_id.name}")
            else:
                _logger.warning("No deal_id - cannot apply template to unsaved deal")
            
            return {'type': 'ir.actions.act_window_close'}
    
    def action_skip(self):
        """Skip template selection - manual configuration"""
        self.ensure_one()
        
        _logger.info("User skipped template selection")
        
        # Return with skip flag
        return {
            'type': 'ir.actions.act_window_close',
            'context': {
                'template_selection_skipped': True,
            }
        }