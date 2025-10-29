from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmDealTemplate(models.Model):
    """Deal Template with Complete Functionality
    
    SPRINT v2-4 COMPLETE VERSION:
    - Hierarchy: product → category → generic
    - Dual commercial terms (sales/purchase)
    - Incoterm locations with smart defaults
    - Lead times for wizard calculations
    - Mail tracking
    """
    _name = 'dm.deal.template'
    _description = 'Deal Template'
    _order = 'priority desc, id desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    
    name = fields.Char(
        string='Template Name',
        required=True,
        tracking=True,
        help='Descriptive name for this template'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        tracking=True,
        help='Uncheck to archive template'
    )
    
    priority = fields.Integer(
        string='Priority',
        default=10,
        help='Higher priority = more specific. Product-specific=30, Category=20, Generic=10'
    )
    
    # Template Type (hierarchy)
    template_type = fields.Selection([
        ('product', 'Product Specific'),
        ('category', 'Product Category'),
        ('generic', 'Generic/Default')
    ], string='Template Type', required=True, default='generic', tracking=True)
    
    # Applicability Criteria
    product_id = fields.Many2one(
        'product.product',
        string='Specific Product',
        domain=[('sale_ok', '=', True)],
        help='Template applies to this specific product'
    )
    
    product_category_id = fields.Many2one(
        'product.category',
        string='Product Category',
        help='Template applies to products in this category'
    )
    
    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        domain=[('is_company', '=', True)],
        help='Template applies to this customer'
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        string='Supplier',
        domain=[('is_company', '=', True)],
        help='Template applies to this supplier'
    )
    
    # SALES Commercial Terms
    sale_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Sales Payment Terms',
        help='Default payment terms for customer'
    )
    
    sale_incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Sales Incoterm',
        help='Default delivery terms for customer (e.g., FOB, CIF)'
    )
    
    sale_incoterm_location = fields.Char(
        string='Sales Incoterm Location',
        help='Optional: Specific delivery location. If blank, uses Port of Discharge from deal'
    )
    
    # PURCHASE Commercial Terms
    purchase_payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Purchase Payment Terms',
        help='Default payment terms for supplier'
    )
    
    purchase_incoterm_id = fields.Many2one(
        'account.incoterms',
        string='Purchase Incoterm',
        help='Default delivery terms from supplier (e.g., EXW, FOB)'
    )
    
    purchase_incoterm_location = fields.Char(
        string='Purchase Incoterm Location',
        help='Optional: Specific pickup location. If blank, uses Port of Loading from deal'
    )
    
    # Logistics
    loading_port_id = fields.Many2one(
        'dm.port',
        string='Default Loading Port',
        help='Port where goods are picked up from supplier'
    )
    
    discharge_port_id = fields.Many2one(
        'dm.port',
        string='Default Discharge Port',
        help='Port where goods arrive for customer'
    )
    
    # Invoice Configuration
    invoice_split = fields.Boolean(
        string='Split Invoice',
        default=True,
        help='Split into product invoice and service invoice'
    )
    
    product_invoice_percentage = fields.Float(
        string='Product Invoice %',
        default=85.0,
        digits=(5, 2),
        help='Percentage of total to invoice as product (rest is service)'
    )
    
    service_invoice_percentage = fields.Float(
        string='Service Invoice %',
        compute='_compute_service_percentage',
        store=True,
        digits=(5, 2)
    )
    
    # Lead Times (for wizard calculations)
    total_lead_time = fields.Integer(
        string='Total Lead Time (days)',
        default=45,
        help='Total time from order to delivery. Used by wizard to calculate RTS from ETA.'
    )
    
    production_lead_time = fields.Integer(
        string='Production Lead Time (days)',
        default=21,
        help='Time needed for production. Used to calculate production start from RTS.'
    )
    
    transit_lead_time = fields.Integer(
        string='Transit Lead Time (days)',
        default=24,
        help='Time for shipment from POL to POD. Used to calculate ETD from ETA.'
    )
    
    # Company (for multi-company environments)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company
    )
    
    notes = fields.Text(
        string='Notes',
        help='Additional information about this template'
    )
    
    @api.depends('product_invoice_percentage')
    def _compute_service_percentage(self):
        for template in self:
            template.service_invoice_percentage = 100.0 - template.product_invoice_percentage
    
    @api.constrains('template_type', 'product_id', 'product_category_id')
    def _check_template_consistency(self):
        """Ensure template type matches populated fields"""
        for template in self:
            if template.template_type == 'product':
                if not template.product_id:
                    raise ValidationError(_('Product-specific templates must have a product selected'))
                # Auto-set priority
                if template.priority < 30:
                    template.priority = 30
            
            elif template.template_type == 'category':
                if not template.product_category_id:
                    raise ValidationError(_('Category templates must have a product category selected'))
                if template.product_id:
                    raise ValidationError(_('Category template cannot have a specific product'))
                # Auto-set priority
                if template.priority < 20:
                    template.priority = 20
            
            elif template.template_type == 'generic':
                if template.product_id or template.product_category_id:
                    raise ValidationError(_('Generic template cannot have product or category specified'))
                # Auto-set priority
                if template.priority < 10:
                    template.priority = 10
    
    @api.constrains('product_invoice_percentage')
    def _check_invoice_percentage(self):
        """Validate invoice split percentages"""
        for template in self:
            if template.invoice_split:
                if not 0 <= template.product_invoice_percentage <= 100:
                    raise ValidationError(_("Product invoice percentage must be between 0 and 100"))
    
    @api.model
    def find_best_template(self, product_id=None, category_id=None, customer_id=None, supplier_id=None, return_all=False):
        """
        Find matching template(s) with enhanced disambiguation support.
        
        Priority order:
        1. Product-specific (priority 30)
        2. Category (priority 20)
        3. Generic (priority 10)
        
        Args:
            product_id: Product ID to match
            category_id: Product category ID to match
            customer_id: Customer ID to match
            supplier_id: Supplier ID to match
            return_all: If True, return all matches at highest priority level (for disambiguation)
                       If False, return single template or False if ambiguous
        
        Returns:
            - If return_all=False: Single template record or False
            - If return_all=True: Recordset of all matching templates (may be empty)
        """
        domain = [('active', '=', True)]
        
        # Add customer/supplier filters
        if customer_id:
            domain.append('|')
            domain.append(('customer_id', '=', customer_id))
            domain.append(('customer_id', '=', False))
        
        if supplier_id:
            domain.append('|')
            domain.append(('supplier_id', '=', supplier_id))
            domain.append(('supplier_id', '=', False))
        
        # Search all potential templates
        templates = self.search(domain, order='priority desc, id desc')
        
        if not templates:
            _logger.warning("No applicable templates found")
            return self.browse() if return_all else False
        
        # Filter by product hierarchy
        matching_templates = self.browse()
        
        if product_id:
            # Try product-specific first (priority 30)
            product_templates = templates.filtered(
                lambda t: t.template_type == 'product' and t.product_id.id == product_id
            )
            if product_templates:
                matching_templates = product_templates
                _logger.info(f"Found {len(product_templates)} product-specific template(s)")
            
            # Then try category (priority 20)
            elif category_id:
                category_templates = templates.filtered(
                    lambda t: t.template_type == 'category' and t.product_category_id.id == category_id
                )
                if category_templates:
                    matching_templates = category_templates
                    _logger.info(f"Found {len(category_templates)} category template(s)")
        
        # Finally, generic (priority 10)
        if not matching_templates:
            generic_templates = templates.filtered(lambda t: t.template_type == 'generic')
            if generic_templates:
                matching_templates = generic_templates
                _logger.info(f"Found {len(generic_templates)} generic template(s)")
        
        # Return based on mode
        if return_all:
            return matching_templates
        else:
            # Single template mode - check for ambiguity
            if len(matching_templates) == 0:
                return False
            elif len(matching_templates) == 1:
                return matching_templates[0]
            else:
                # Multiple matches - ambiguous
                _logger.warning(f"Ambiguous: {len(matching_templates)} templates match")
                return False    
                
    def get_template_values(self):
        """Get dictionary of values to apply to deal"""
        self.ensure_one()
        
        values = {}
        
        # Sales payment and commercial terms
        if self.sale_payment_term_id:
            values['sale_payment_term_id'] = self.sale_payment_term_id.id
        
        if self.sale_incoterm_id:
            values['sale_incoterm_id'] = self.sale_incoterm_id.id
        
        if self.sale_incoterm_location:
            values['sale_incoterm_location'] = self.sale_incoterm_location
        
        # Purchase payment and commercial terms
        if self.purchase_payment_term_id:
            values['purchase_payment_term_id'] = self.purchase_payment_term_id.id
        
        if self.purchase_incoterm_id:
            values['purchase_incoterm_id'] = self.purchase_incoterm_id.id
        
        if self.purchase_incoterm_location:
            values['purchase_incoterm_location'] = self.purchase_incoterm_location
        
        # Ports
        if self.loading_port_id:
            values['loading_port_id'] = self.loading_port_id.id
        
        if self.discharge_port_id:
            values['discharge_port_id'] = self.discharge_port_id.id
        
        # Invoice split
        values['invoice_split'] = self.invoice_split
        if self.invoice_split:
            values['product_invoice_percentage'] = self.product_invoice_percentage
            values['service_invoice_percentage'] = self.service_invoice_percentage
        
        return values
    
    @api.model
    def create(self, vals):
        """Set priority based on template type"""
        if 'priority' not in vals:
            template_type = vals.get('template_type', 'generic')
            vals['priority'] = {
                'product': 30,
                'category': 20,
                'generic': 10
            }.get(template_type, 10)
        
        return super().create(vals)
    
    @api.model
    def create_default_templates(self):
        """Create default templates for initial setup"""
        
        # Check if we already have templates
        if self.search_count([]) > 0:
            _logger.info("Templates already exist, skipping default creation")
            return
        
        # Create generic template
        self.create({
            'name': 'Generic Default',
            'template_type': 'generic',
            'priority': 10,
            'invoice_split': True,
            'product_invoice_percentage': 85.0,
            'total_lead_time': 45,
            'production_lead_time': 21,
            'transit_lead_time': 24,
            'notes': 'Default template for all deals'
        })
        
        _logger.info("Default generic template created")
    
    def name_get(self):
        """Display template with type indicator"""
        result = []
        for template in self:
            type_icon = {
                'product': '🎯',
                'category': '📁',
                'generic': '⚙️'
            }.get(template.template_type, '')
            
            name = f"{type_icon} {template.name}"
            result.append((template.id, name))
        
        return result