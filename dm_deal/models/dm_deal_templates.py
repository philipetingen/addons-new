from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmDealTemplates(models.Model):
    """Deal Templates Extension - Template Selection and Application"""
    _inherit = 'dm.deal'
    _description = 'Deal - Templates Extension'
    
    # ============================================================
    # TEMPLATE ONCHANGE METHODS
    # ============================================================
    
    @api.onchange('line_ids')
    def _onchange_apply_template(self):
        """
        Enhanced onchange with template validation for subsequent lines.
        """
        if not self.line_ids or self._context.get('no_template'):
            return
        
        # Skip if in template selection process
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
        """
        self.ensure_one()
        
        if not self.line_ids or not self.template_id:
            return
        
        # Get last (most recently added) line
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
        if not self.line_ids:
            return
        
        first_line = self.line_ids[0]
        product = first_line.product_id
        
        if not product:
            return
        
        # Use LINE's supplier, not deal's
        line_supplier = first_line.supplier_id
        supplier_filter = line_supplier.id if line_supplier else None
        
        _logger.info(f"Template search for {product.name}, supplier: {line_supplier.name if line_supplier else 'Any'}")
        
        # Find matching templates
        matching_templates = self.env['dm.deal.template'].find_best_template(
            product_id=product.id,
            category_id=product.categ_id.id,
            customer_id=self.customer_id.id,
            supplier_id=supplier_filter,
            return_all=True
        )
        
        template_count = len(matching_templates)
        
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
            self._apply_single_template(template)
            
            return {
                'warning': {
                    'title': _('Template Applied'),
                    'message': _(f"Template '{template.name}' applied.")
                }
            }
        
        else:
            self.template_selection_pending = True
            return self._open_template_selection_wizard(matching_templates)

    def _apply_single_template(self, template):
        """Apply template and sync supplier to deal header"""
        self.ensure_one()
        
        # Apply commercial terms
        self.apply_template(template)
        
        # Set template_id
        self.template_id = template
        
        # Copy supplier from first line to deal header
        if self.line_ids and self.line_ids[0].supplier_id:
            line_supplier = self.line_ids[0].supplier_id
            if not self.supplier_id:
                self.supplier_id = line_supplier
                _logger.info(f"Copied supplier from line to deal: {line_supplier.name}")
            elif self.supplier_id != line_supplier:
                _logger.warning(f"Deal supplier mismatch!")
        
        # Alternative: Use template supplier if available
        elif template.supplier_id and not self.supplier_id:
            self.supplier_id = template.supplier_id
            _logger.info(f"Set supplier from template: {template.supplier_id.name}")
        
        self.template_selection_pending = False

    def _open_template_selection_wizard(self, templates):
        """Open wizard for template selection"""
        wizard_vals = {
            'template_ids': [(6, 0, templates.ids)],
        }
        
        # Only set deal_id if deal is saved
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

    def apply_selected_template_from_wizard(self, template_id):
        """
        Apply template selected from wizard.
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
        """Apply template settings to deal"""
        self.ensure_one()
        
        if not template:
            return
        
        values = {}
        
        # Get valid field names
        valid_fields = set(self._fields.keys())
        
        # Template field mapping
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
        
        # Only add fields that exist
        for field_name, field_value in template_field_mapping.items():
            if field_name in valid_fields and field_value:
                values[field_name] = field_value
        
        # Apply values
        if values:
            self.write(values)
            _logger.info(f"Applied template {template.name} to deal {self.name}")
        
        return True
    
    def action_select_template(self):
        """
        Manual action to open template selection wizard.
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