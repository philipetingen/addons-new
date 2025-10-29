# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DealCreationWizard(models.TransientModel):
    _name = 'dm.deal.creation.wizard'
    _description = 'Deal Creation Wizard'
    
    # Wizard state management
    current_step = fields.Selection([
        ('step1_header', 'Step 1: Deal Header'),
        ('step2_products', 'Step 2: Add Products'),
        ('step3_review', 'Step 3: Review & Create')
    ], default='step1_header', required=True)
    
    # ===== STEP 1: DEAL HEADER =====
    
    # Required fields
    customer_id = fields.Many2one(
        'res.partner',
        string='Customer',
        required=True,
        domain=[('is_company', '=', True), ('customer_rank', '>', 0)],
        help="Select the customer for this deal"
    )
    
    customer_po_number = fields.Char(
        string='Customer PO#',
        required=True,
        help="Customer's purchase order number (must be unique)"
    )
    
    po_date = fields.Date(
        string='PO Date',
        required=True,
        default=fields.Date.today,
        help="Date of customer purchase order"
    )
    
    # Optional fields with smart defaults
    eta_requested = fields.Date(
        string='ETA Requested',
        help="Estimated Time of Arrival requested by customer"
    )
    
    rts_requested = fields.Date(
        string='RTS Requested',
        help="Ready to Ship date (auto-calculated from ETA if left blank)"
    )
    
    # Template info (loaded from customer)
    template_id = fields.Many2one(
        'dm.deal.template',
        string='Deal Template',
        help="Template loaded based on customer/product selection"
    )
    
    # Computed fields for display
    customer_payment_term_id = fields.Many2one(
        'account.payment.term',
        related='customer_id.property_payment_term_id',
        string='Customer Payment Terms'
    )
     
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
    )
 
    # ===== STEP 2: PRODUCT LINES =====
    
    line_ids = fields.One2many(
        'dm.deal.creation.wizard.line',
        'wizard_id',
        string='Product Lines'
    )
    
    line_count = fields.Integer(
        compute='_compute_line_count',
        string='Line Count'
    )
    
    # ===== STEP 3: REVIEW =====
    
    total_amount = fields.Monetary(
        compute='_compute_totals',
        string='Total Amount',
        currency_field='currency_id'
    )
    
    total_weight = fields.Float(
        compute='_compute_totals',
        string='Total Weight (kg)',
        digits=(16, 3)
    )
    
    # Validation warnings
    moq_warning_count = fields.Integer(
        compute='_compute_validation_warnings',
        string='MOQ Warnings'
    )
    
    has_warnings = fields.Boolean(
        compute='_compute_validation_warnings',
        string='Has Warnings'
    )
    
    # ===== COMPUTED FIELDS =====
    
    @api.depends('line_ids')
    def _compute_line_count(self):
        for wizard in self:
            wizard.line_count = len(wizard.line_ids)
    
    @api.depends('line_ids.amount_sale', 'line_ids.weight')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_amount = sum(wizard.line_ids.mapped('amount_sale'))
            wizard.total_weight = sum(wizard.line_ids.mapped('weight'))
    
    @api.depends('line_ids.moq_status')
    def _compute_validation_warnings(self):
        for wizard in self:
            moq_warnings = wizard.line_ids.filtered(lambda l: l.moq_status == 'below')
            wizard.moq_warning_count = len(moq_warnings)
            wizard.has_warnings = wizard.moq_warning_count > 0
            
    @api.onchange('line_ids')
    def _onchange_line_ids_update_currency(self):
        """Update currency from first line with pricing"""
        if self.line_ids and not self.currency_id:
            # Get currency from customer's pricelist
            if self.customer_id and self.customer_id.property_product_pricelist:
                self.currency_id = self.customer_id.property_product_pricelist.currency_id           
    
    # ===== ONCHANGE METHODS =====
    
    @api.onchange('customer_id')
    def _onchange_customer_load_template(self):
        """Load deal template and currency when customer is selected"""
        if self.customer_id:
            _logger.info(f"Customer selected: {self.customer_id.name}")
            
            # Find generic template for this customer
            template = self.env['dm.deal.template'].find_best_template(
                customer_id=self.customer_id.id
            )
            if template:
                self.template_id = template
                _logger.info(f"Template loaded: {template.name}")
            
            # Set currency from customer's pricelist
            if self.customer_id.property_product_pricelist:
                self.currency_id = self.customer_id.property_product_pricelist.currency_id
                _logger.info(
                    f"Currency set from pricelist: {self.currency_id.name} "
                    f"(Pricelist: {self.customer_id.property_product_pricelist.name})"
                )
            else:
                self.currency_id = self.env.company.currency_id
                _logger.info(f"No pricelist, using company currency: {self.currency_id.name}")
    
    @api.onchange('eta_requested', 'template_id')
    def _onchange_eta_calculate_rts(self):
        """Calculate RTS from ETA if not manually entered"""
        if self.eta_requested and not self.rts_requested:
            # Get transit time from template or use default
            if self.template_id and self.template_id.total_lead_time:
                lead_time = self.template_id.total_lead_time
            else:
                # Conservative default: 30 days transit + 7 days buffer
                lead_time = 37
            
            self.rts_requested = self.eta_requested - timedelta(days=lead_time)
    
    @api.onchange('po_date')
    def _onchange_po_date_warning(self):
        """Warn if PO date is in the future"""
        if self.po_date and self.po_date > fields.Date.today():
            return {
                'warning': {
                    'title': _('Future PO Date'),
                    'message': _('PO date is in the future. This is unusual but allowed.')
                }
            }
    
    # ===== NAVIGATION ACTIONS =====
    
    def action_next_step(self):
        """Move to next wizard step"""
        self.ensure_one()
        
        if self.current_step == 'step1_header':
            # Validate header before moving to products
            self._validate_header()
            self.current_step = 'step2_products'
            
        elif self.current_step == 'step2_products':
            # Validate at least one line exists
            if not self.line_ids:
                raise UserError(_('Please add at least one product line before proceeding.'))
            self.current_step = 'step3_review'
        
        return self._reopen_wizard()
    
    def action_previous_step(self):
        """Move to previous wizard step"""
        self.ensure_one()
        
        if self.current_step == 'step3_review':
            self.current_step = 'step2_products'
        elif self.current_step == 'step2_products':
            self.current_step = 'step1_header'
        
        return self._reopen_wizard()
    
    def action_add_product_line(self):
        """Open wizard to add new product line"""
        self.ensure_one()
        
        return {
            'name': _('Add Product Line'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.line.add.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_parent_wizard_id': self.id,
                'default_customer_id': self.customer_id.id,
            }
        }
    
    # ===== VALIDATION =====
    
    def _validate_header(self):
        """Validate step 1 data"""
        self.ensure_one()
        
        if not self.customer_id:
            raise ValidationError(_('Customer is required.'))
        
        if not self.customer_po_number:
            raise ValidationError(_('Customer PO# is required.'))
        
        # Check for duplicate PO number
        existing = self.env['dm.deal'].search([
            ('customer_id', '=', self.customer_id.id),
            ('customer_po_number', '=', self.customer_po_number)
        ], limit=1)
        
        if existing:
            raise ValidationError(_(
                'Customer PO# %s already exists for this customer in Deal %s.\n'
                'Please use a different PO number or edit the existing deal.'
            ) % (self.customer_po_number, existing.name))
        
        if not self.po_date:
            raise ValidationError(_('PO Date is required.'))
    
    # ===== CREATE DEAL =====
    
    def action_create_deal(self):
        """
        Create the deal from wizard data with full automation.
        
        This method:
        1. Pre-validates vendor pricing exists
        2. Creates deal + lines
        3. Triggers supplier determination (sets line.supplier_id + purchase price)
        4. Triggers template application (handles selection if multiple)
        5. Creates SO/PO via validation
        """
        self.ensure_one()
        
        # STEP 0: PRE-VALIDATION - Check if all products have vendor pricing
        _logger.info("🔍 Pre-validation: Checking vendor pricing")
        
        for wizard_line in self.line_ids:
            # Check if vendor pricing exists for this product
            supplier_infos = self.env['product.supplierinfo'].search([
                '|',
                    ('product_id', '=', wizard_line.product_id.id),
                    '&',
                        ('product_id', '=', False),
                        ('product_tmpl_id', '=', wizard_line.product_id.product_tmpl_id.id),
            ], limit=1)
            
            if not supplier_infos:
                raise UserError(
                    f"Cannot create deal!\n\n"
                    f"Product '{wizard_line.product_id.name}' has no vendor pricing configured.\n\n"
                    f"Please configure vendor pricing in the product's Purchase tab before creating the deal."
                )
        
        _logger.info("   ✅ All products have vendor pricing")
        
        # Final validation
        if not self.line_ids:
            raise UserError(_('Cannot create deal without product lines.'))
        
        _logger.info(f"🎬 Starting deal creation from wizard")
        _logger.info(f"   Customer: {self.customer_id.name}")
        _logger.info(f"   PO#: {self.customer_po_number}")
        _logger.info(f"   Lines: {len(self.line_ids)}")
        
        try:
            # STEP 1: Create deal header
            _logger.info("📋 Step 1: Creating deal record")
            deal = self._create_deal_record()
            _logger.info(f"   ✅ Deal created: {deal.name}")
            
            # STEP 2: Create deal lines
            _logger.info("📦 Step 2: Creating deal lines")
            self._create_deal_lines(deal)
            _logger.info(f"   ✅ Created {len(deal.line_ids)} lines")
            
            # STEP 3: Trigger supplier determination for each line
            # This is what normally happens in onchange but doesn't fire during create()
            _logger.info("🏭 Step 3: Determining suppliers and purchase prices")
            for idx, line in enumerate(deal.line_ids, 1):
                _logger.info(f"   Processing line {idx}: {line.product_id.name}")
                
                # This method sets line.supplier_id and price_packaging_purchase
                line._fetch_supplier_price()
                
                _logger.info(f"   ✅ Line {idx} supplier: {line.supplier_id.name if line.supplier_id else 'NOT SET'}")
                _logger.info(f"   ✅ Line {idx} purchase price: ${line.price_packaging_purchase:.6f}")
            
            # STEP 4: Set deal supplier from first line
            if deal.line_ids and deal.line_ids[0].supplier_id:
                deal.supplier_id = deal.line_ids[0].supplier_id
                _logger.info(f"🏢 Step 4: Deal supplier set to: {deal.supplier_id.name}")
            else:
                _logger.warning("⚠️ No supplier determined - may need manual selection")
            
            # STEP 5: Apply template
            # This may open template selection wizard if multiple matches
            _logger.info("📋 Step 5: Applying deal template")
            template_result = deal._apply_template_from_lines()
            
            if template_result and isinstance(template_result, dict) and template_result.get('type') == 'ir.actions.act_window':
                # Template selection wizard opened
                _logger.info("   📋 Multiple templates - selection wizard opened")
                # Return the wizard action - user will select template, then deal opens
                return template_result
            
            if deal.template_id:
                _logger.info(f"   ✅ Template applied: {deal.template_id.name}")
            else:
                _logger.warning("   ⚠️ No template applied")
            
            # STEP 6: Validate deal (creates SO/PO)
            _logger.info("✅ Step 6: Validating deal (creates SO/PO)")
            deal.action_validate()
            
            _logger.info(f"🎉 Deal {deal.name} created successfully!")
            _logger.info(f"   SO: {deal.sale_order_ids.mapped('name')}")
            _logger.info(f"   PO: {deal.purchase_order_ids.mapped('name')}")
            
            # Return action to open the created deal
            return {
                'name': _('Deal Created'),
                'type': 'ir.actions.act_window',
                'res_model': 'dm.deal',
                'res_id': deal.id,
                'view_mode': 'form',
                'target': 'current',
            }
            
        except Exception as e:
            _logger.error(f"❌ Deal creation failed: {str(e)}", exc_info=True)
            raise UserError(_(
                'Deal creation failed: %s\n\n'
                'No data has been saved. Please review the error and try again.'
            ) % str(e))
    
    def _create_deal_record(self):
        """Create the dm.deal record"""
        deal_vals = {
            'customer_id': self.customer_id.id,
            'customer_po_number': self.customer_po_number,
            'po_date': self.po_date,
            'rts_requested': self.rts_requested,
            'eta_requested': self.eta_requested,
        }
        
        return self.env['dm.deal'].create(deal_vals)
    
    def _create_deal_lines(self, deal):
        """Create all deal lines"""
        for wizard_line in self.line_ids:
            line_vals = {
                'deal_id': deal.id,
                'product_id': wizard_line.product_id.id,
                'product_packaging_id': wizard_line.packaging_id.id,  # Different field name
                'entry_mode': wizard_line.entry_mode,
                'quantity_packaging': wizard_line.quantity_packaging,
                'weight': wizard_line.weight,
                'price_packaging_sale': wizard_line.price_packaging_sale,
                'customer_product_code': wizard_line.customer_product_code,
            }
            
            self.env['dm.deal.line'].create(line_vals)
    
    # ===== HELPER METHODS =====
    
    def _reopen_wizard(self):
        """Reopen wizard at current step with correct view"""
        view_mapping = {
            'step1_header': 'dm_deal.view_deal_creation_wizard_step1',
            'step2_products': 'dm_deal.view_deal_creation_wizard_step2',
            'step3_review': 'dm_deal.view_deal_creation_wizard_step3',
        }
        
        view_xmlid = view_mapping.get(self.current_step, 'dm_deal.view_deal_creation_wizard_step1')
        
        try:
            view_id = self.env.ref(view_xmlid).id
        except Exception as e:
            _logger.warning(f"Could not load view {view_xmlid}: {e}")
            view_id = False
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'dm.deal.creation.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'view_id': view_id,
            'target': 'new',
            'context': {'dialog_size': 'extra-large'},  # â† ADD THIS
        }