from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmInvoiceGenerationWizard(models.TransientModel):
    """
    Wizard for generating invoices from shipment loading confirmation.
    Handles both single invoices and 80/20 split invoices.
    Uses ACTUAL loaded quantities as basis for invoicing.
    """
    _name = 'dm.invoice.generation.wizard'
    _description = 'Invoice Generation Wizard'
    
    # Configuration
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        readonly=True
    )
    
    split_config_id = fields.Many2one(
        'dm.invoice.split.config',
        string='Split Configuration'
    )
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        compute='_compute_shipment_id',
        store=True
    )
    
    generate_split = fields.Boolean(
        string='Generate Split Invoices',
        compute='_compute_generate_split',
        store=True,
        readonly=False
    )
    
    # Currency
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        readonly=True
    )
    
    # Incoterm validation
    sale_incoterm_id = fields.Many2one(
        'account.incoterms',
        related='deal_id.sale_incoterm_id',
        readonly=True
    )
    
    # Preview amounts - Product Invoice
    product_amount = fields.Monetary(
        string='Product Invoice Amount',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    product_dp = fields.Monetary(
        string='Product Downpayment',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    product_due = fields.Monetary(
        string='Product Amount Due',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    # Preview amounts - Service Invoice
    service_amount = fields.Monetary(
        string='Service Invoice Amount',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    service_dp = fields.Monetary(
        string='Service Downpayment',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    service_due = fields.Monetary(
        string='Service Amount Due',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    # Service components breakdown
    service_base_amount = fields.Monetary(
        string='Service Base (% of Goods)',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    freight_amount = fields.Monetary(
        string='Freight Charges',
        currency_field='currency_id',
        readonly=False
    )
    
    insurance_amount = fields.Monetary(
        string='Insurance Charges',
        currency_field='currency_id',
        readonly=False
    )
    
    # Total amounts
    total_amount = fields.Monetary(
        string='Total Invoice Amount',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    total_downpayment = fields.Monetary(
        string='Total Downpayment Applied',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    total_due = fields.Monetary(
        string='Total Amount Due',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True
    )
    
    # Line details from actual shipment
    line_ids = fields.One2many(
        'dm.invoice.generation.wizard.line',
        'wizard_id',
        string='Invoice Lines'
    )
    
    # Validation flags
    has_loaded_quantities = fields.Boolean(
        compute='_compute_validation_flags',
        store=True
    )
    
    incoterm_validation_message = fields.Text(
        compute='_compute_validation_flags',
        store=True
    )
    
    # Invoice creation options
    create_draft = fields.Boolean(
        string='Create as Draft',
        default=False,
        help='Create invoices in draft state for review'
    )
    
    invoice_date = fields.Date(
        string='Invoice Date',
        default=fields.Date.today,
        required=True
    )
    
    payment_term_id = fields.Many2one(
        'account.payment.term',
        string='Payment Terms',
        compute='_compute_payment_term',
        store=True,
        readonly=False
    )
    
    @api.depends('deal_id')
    def _compute_shipment_id(self):
        """Get shipment from deal"""
        for wizard in self:
            wizard.shipment_id = wizard.deal_id.shipment_id if wizard.deal_id else False
    
    @api.depends('deal_id', 'split_config_id')
    def _compute_generate_split(self):
        """Determine if split invoices should be generated"""
        for wizard in self:
            if wizard.split_config_id:
                wizard.generate_split = True
            else:
                wizard.generate_split = wizard.deal_id.invoice_split != 'no' if wizard.deal_id else False
    
    @api.depends('deal_id')
    def _compute_payment_term(self):
        """Get default payment term from deal"""
        for wizard in self:
            wizard.payment_term_id = wizard.deal_id.payment_term_id if wizard.deal_id else False
    
    @api.depends('line_ids', 'line_ids.quantity', 'line_ids.price_unit')
    def _compute_validation_flags(self):
        """Check validation conditions"""
        for wizard in self:
            wizard.has_loaded_quantities = bool(wizard.line_ids)
            
            # Incoterm validation
            message = ""
            if wizard.sale_incoterm_id:
                if wizard.sale_incoterm_id.code in ['CFR', 'CIF'] and not wizard.freight_amount:
                    message = _("Warning: %s terms require freight charges") % wizard.sale_incoterm_id.code
                elif wizard.sale_incoterm_id.code == 'CIF' and not wizard.insurance_amount:
                    message = _("Warning: CIF terms require insurance charges")
            
            wizard.incoterm_validation_message = message
    
    @api.depends('line_ids', 'line_ids.quantity', 'line_ids.price_unit',
                 'generate_split', 'freight_amount', 'insurance_amount')
    def _compute_amounts(self):
        """Calculate all invoice amounts based on actual loaded quantities"""
        for wizard in self:
            # Calculate goods total from lines
            goods_total = sum(wizard.line_ids.mapped('subtotal'))
            
            if wizard.generate_split and wizard.split_config_id:
                # Use split configuration percentages
                config = wizard.split_config_id
                
                # Product invoice (percentage of goods only)
                wizard.product_amount = goods_total * (config.product_percentage / 100.0)
                
                # Service invoice (percentage of goods + freight/insurance)
                wizard.service_base_amount = goods_total * (config.service_percentage / 100.0)
                wizard.service_amount = wizard.service_base_amount + wizard.freight_amount + wizard.insurance_amount
                
                wizard.total_amount = wizard.product_amount + wizard.service_amount
            else:
                # Single invoice
                wizard.product_amount = goods_total
                wizard.service_amount = 0
                wizard.service_base_amount = 0
                wizard.total_amount = goods_total
            
            # Calculate downpayment allocation
            dp_requests = wizard.env['dm.downpayment.request'].search([
                ('deal_id', '=', wizard.deal_id.id),
                ('request_type', '=', 'customer'),
                ('state', '=', 'paid')
            ])
            
            wizard.total_downpayment = sum(dp_requests.mapped('amount_received'))
            
            # Pro-rata allocation
            if wizard.total_amount > 0:
                if wizard.generate_split:
                    product_ratio = wizard.product_amount / wizard.total_amount
                    service_ratio = wizard.service_amount / wizard.total_amount
                    
                    wizard.product_dp = wizard.total_downpayment * product_ratio
                    wizard.service_dp = wizard.total_downpayment * service_ratio
                else:
                    wizard.product_dp = wizard.total_downpayment
                    wizard.service_dp = 0
            else:
                wizard.product_dp = wizard.service_dp = 0
            
            # Calculate due amounts
            wizard.product_due = wizard.product_amount - wizard.product_dp
            wizard.service_due = wizard.service_amount - wizard.service_dp
            wizard.total_due = wizard.total_amount - wizard.total_downpayment
    
    @api.model
    def default_get(self, fields_list):
        """Initialize wizard with shipment data"""
        res = super().default_get(fields_list)
        
        # Get deal from context
        deal_id = self.env.context.get('default_deal_id')
        if not deal_id:
            active_id = self.env.context.get('active_id')
            active_model = self.env.context.get('active_model')
            if active_model == 'dm.deal':
                deal_id = active_id
        
        if deal_id:
            deal = self.env['dm.deal'].browse(deal_id)
            res['deal_id'] = deal_id
            
            # Get split configuration
            if deal.invoice_split_config_id:
                res['split_config_id'] = deal.invoice_split_config_id.id
                res['freight_amount'] = deal.invoice_split_config_id.freight_amount
                res['insurance_amount'] = deal.invoice_split_config_id.insurance_amount
            
            # Load actual shipped quantities
            if deal.shipment_id:
                lines = []
                for ship_line in deal.shipment_id.line_ids.filtered(lambda l: l.deal_id == deal):
                    if ship_line.deal_line_id:
                        lines.append((0, 0, {
                            'product_id': ship_line.deal_line_id.product_id.id,
                            'product_packaging_id': ship_line.deal_line_id.packaging_id.id,
                            'quantity': ship_line.actual_quantity_loaded,  # ACTUAL loaded quantity
                            'price_unit': ship_line.deal_line_id.price_packaging_sale,
                            'deal_line_id': ship_line.deal_line_id.id,
                            'shipment_line_id': ship_line.id,
                        }))
                res['line_ids'] = lines
        
        return res
    
    def action_generate(self):
        """Generate invoices based on configuration"""
        self.ensure_one()
        
        if not self.has_loaded_quantities:
            raise UserError(_('No loaded quantities found. Cannot generate invoices.'))
        
        # Validate Incoterm requirements
        if self.incoterm_validation_message:
            if self.sale_incoterm_id.code == 'CIF' and not self.insurance_amount:
                raise UserError(_('CIF terms require insurance charges.'))
            elif self.sale_incoterm_id.code in ['CFR', 'CIF'] and not self.freight_amount:
                raise UserError(_('CFR/CIF terms require freight charges.'))
        
        AccountMove = self.env['account.move']
        invoices = AccountMove
        
        # Get downpayments to apply
        dp_requests = self.env['dm.downpayment.request'].search([
            ('deal_id', '=', self.deal_id.id),
            ('request_type', '=', 'customer'),
            ('state', '=', 'paid')
        ])
        
        if self.generate_split:
            # Generate two invoices
            invoices |= self._create_product_invoice(dp_requests)
            invoices |= self._create_service_invoice(dp_requests)
            
            # Update split configuration
            if self.split_config_id:
                self.split_config_id.write({
                    'product_invoice_id': invoices.filtered('is_product_invoice').id,
                    'service_invoice_id': invoices.filtered('is_service_invoice').id,
                    'state': 'invoiced',
                    'freight_amount': self.freight_amount,
                    'insurance_amount': self.insurance_amount,
                })
        else:
            # Generate single invoice
            invoices = self._create_single_invoice(dp_requests)
        
        # Post invoices if not draft
        if not self.create_draft:
            invoices.action_post()
        
        # Update deal
        self.deal_id.message_post(
            body=_('Invoices generated from shipment loading: %s') % ', '.join(invoices.mapped('name'))
        )
        
        # Return action to show invoices
        if len(invoices) == 1:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'account.move',
                'res_id': invoices.id,
                'view_mode': 'form',
            }
        else:
            return {
                'type': 'ir.actions.act_window',
                'name': _('Generated Invoices'),
                'res_model': 'account.move',
                'view_mode': 'tree,form',
                'domain': [('id', 'in', invoices.ids)],
            }
    
    def _create_product_invoice(self, dp_requests):
        """Create product invoice (goods only or percentage of goods)"""
        self.ensure_one()
        
        invoice_lines = []
        
        if self.generate_split and self.split_config_id:
            # Apply percentage to each line
            percentage = self.split_config_id.product_percentage / 100.0
            for line in self.line_ids:
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': f"{line.product_id.display_name} ({self.split_config_id.product_percentage}% Product)",
                    'quantity': line.quantity * percentage,
                    'product_uom_id': line.product_packaging_id.packaging_uom_id.id if line.product_packaging_id else line.product_id.uom_id.id,
                    'price_unit': line.price_unit,
                }))
        else:
            # Full quantities
            for line in self.line_ids:
                invoice_lines.append((0, 0, {
                    'product_id': line.product_id.id,
                    'name': line.product_id.display_name,
                    'quantity': line.quantity,
                    'product_uom_id': line.product_packaging_id.packaging_uom_id.id if line.product_packaging_id else line.product_id.uom_id.id,
                    'price_unit': line.price_unit,
                }))
        
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.deal_id.customer_id.id,
            'invoice_date': self.invoice_date,
            'invoice_payment_term_id': self.payment_term_id.id,
            'ref': f"{self.deal_id.customer_po_number} - Product",
            'dm_deal_id': self.deal_id.id,
            'dm_shipment_id': self.shipment_id.id,
            'is_product_invoice': True,
            'split_config_id': self.split_config_id.id if self.split_config_id else False,
            'invoice_line_ids': invoice_lines,
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        # Apply downpayments
        if dp_requests and self.product_dp > 0:
            self._apply_downpayments(invoice, dp_requests, self.product_dp)
        
        return invoice
    
    def _create_service_invoice(self, dp_requests):
        """Create service invoice (percentage + freight + insurance)"""
        self.ensure_one()
        
        if not self.split_config_id:
            return self.env['account.move']
        
        invoice_lines = []
        
        # Service percentage of goods
        percentage = self.split_config_id.service_percentage / 100.0
        for line in self.line_ids:
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': f"{line.product_id.display_name} ({self.split_config_id.service_percentage}% Service)",
                'quantity': line.quantity * percentage,
                'product_uom_id': line.product_packaging_id.packaging_uom_id.id if line.product_packaging_id else line.product_id.uom_id.id,
                'price_unit': line.price_unit,
            }))
        
        # Add freight charges
        if self.freight_amount > 0:
            freight_product = self._get_or_create_service_product('FREIGHT', 'Ocean Freight Charges')
            invoice_lines.append((0, 0, {
                'product_id': freight_product.id,
                'name': 'Ocean Freight',
                'quantity': 1,
                'price_unit': self.freight_amount,
            }))
        
        # Add insurance charges
        if self.insurance_amount > 0:
            insurance_product = self._get_or_create_service_product('INSURANCE', 'Cargo Insurance')
            invoice_lines.append((0, 0, {
                'product_id': insurance_product.id,
                'name': 'Cargo Insurance',
                'quantity': 1,
                'price_unit': self.insurance_amount,
            }))
        
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.deal_id.customer_id.id,
            'invoice_date': self.invoice_date,
            'invoice_payment_term_id': self.payment_term_id.id,
            'ref': f"{self.deal_id.customer_po_number} - Service",
            'dm_deal_id': self.deal_id.id,
            'dm_shipment_id': self.shipment_id.id,
            'is_service_invoice': True,
            'split_config_id': self.split_config_id.id,
            'invoice_line_ids': invoice_lines,
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        # Apply downpayments
        if dp_requests and self.service_dp > 0:
            self._apply_downpayments(invoice, dp_requests, self.service_dp)
        
        return invoice
    
    def _create_single_invoice(self, dp_requests):
        """Create single invoice (no split)"""
        self.ensure_one()
        
        invoice_lines = []
        for line in self.line_ids:
            invoice_lines.append((0, 0, {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                'quantity': line.quantity,
                'product_uom_id': line.product_packaging_id.packaging_uom_id.id if line.product_packaging_id else line.product_id.uom_id.id,
                'price_unit': line.price_unit,
            }))
        
        invoice_vals = {
            'move_type': 'out_invoice',
            'partner_id': self.deal_id.customer_id.id,
            'invoice_date': self.invoice_date,
            'invoice_payment_term_id': self.payment_term_id.id,
            'ref': self.deal_id.customer_po_number,
            'dm_deal_id': self.deal_id.id,
            'dm_shipment_id': self.shipment_id.id,
            'invoice_line_ids': invoice_lines,
        }
        
        invoice = self.env['account.move'].create(invoice_vals)
        
        # Apply all downpayments
        if dp_requests:
            self._apply_downpayments(invoice, dp_requests, self.total_downpayment)
        
        return invoice
    
    def _apply_downpayments(self, invoice, dp_requests, amount_to_apply):
        """Apply downpayments to invoice"""
        remaining = amount_to_apply
        
        for dp in dp_requests:
            if remaining <= 0:
                break
            
            apply_amount = min(remaining, dp.amount_received)
            dp.apply_to_invoice(invoice.id, apply_amount)
            remaining -= apply_amount
        
        invoice.message_post(
            body=_('Downpayment applied: %s %s') % (amount_to_apply, self.currency_id.symbol)
        )
    
    def _get_or_create_service_product(self, code, name):
        """Get or create service product for freight/insurance"""
        product = self.env['product.product'].search([
            ('default_code', '=', code)
        ], limit=1)
        
        if not product:
            product = self.env['product.product'].create({
                'name': name,
                'default_code': code,
                'type': 'service',
                'sale_ok': True,
                'purchase_ok': False,
            })
        
        return product


class DmInvoiceGenerationWizardLine(models.TransientModel):
    """Invoice line details from actual shipment"""
    _name = 'dm.invoice.generation.wizard.line'
    _description = 'Invoice Generation Line'
    
    wizard_id = fields.Many2one(
        'dm.invoice.generation.wizard',
        required=True,
        ondelete='cascade'
    )
    
    product_id = fields.Many2one(
        'product.product',
        string='Product',
        required=True
    )
    
    product_packaging_id = fields.Many2one(
        'product.packaging',
        string='Packaging'
    )
    
    quantity = fields.Float(
        string='Quantity (Packages)',
        required=True,
        digits='Product Unit of Measure'
    )
    
    price_unit = fields.Float(
        string='Price/Package',
        required=True,
        digits='Product Price'
    )
    
    subtotal = fields.Float(
        string='Subtotal',
        compute='_compute_subtotal',
        store=True
    )
    
    deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line'
    )
    
    shipment_line_id = fields.Many2one(
        'dm.shipment.line',
        string='Shipment Line'
    )
    
    @api.depends('quantity', 'price_unit')
    def _compute_subtotal(self):
        for line in self:
            line.subtotal = line.quantity * line.price_unit