from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmInvoiceSplitConfig(models.Model):
    """
    Manages invoice split configuration for deals.
    Standard split: 80% product invoice, 20% service invoice.
    Service invoice includes: 20% of goods value PLUS freight and insurance charges.
    """
    _name = 'dm.invoice.split.config'
    _description = 'Invoice Split Configuration'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = 'deal_id'
    _sql_constraints = [
        ('deal_unique', 'UNIQUE(deal_id)', 'Only one split configuration allowed per deal!'),
    ]
    
    # Deal link
    deal_id = fields.Many2one(
        'dm.deal',
        'Deal',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True
    )
    
    # Related fields from deal
    customer_id = fields.Many2one(
        'res.partner',
        related='deal_id.customer_id',
        store=True,
        readonly=True
    )
    
    customer_po_number = fields.Char(
        related='deal_id.customer_po_number',
        string='Customer PO#',
        store=True,
        readonly=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        store=True,
        readonly=True
    )
    
    sale_incoterm_id = fields.Many2one(
        'account.incoterms',
        related='deal_id.sale_incoterm_id',
        store=True,
        readonly=True
    )
    
    # Split configuration
    split_type = fields.Selection([
        ('80_20', '80% Product / 20% Service'),
        ('70_30', '70% Product / 30% Service'),
        ('90_10', '90% Product / 10% Service'),
        ('custom', 'Custom Split')
    ], string='Split Type', required=True, default='80_20', tracking=True)
    
    # Custom percentages
    product_percentage = fields.Float(
        'Product %',
        default=80.0,
        tracking=True,
        help='Percentage for product invoice (of goods value only)'
    )
    
    service_percentage = fields.Float(
        'Service %',
        compute='_compute_service_percentage',
        store=True,
        help='Percentage for service invoice (of goods value only)'
    )
    
    # Freight and insurance (ON TOP of service percentage)
    freight_management = fields.Selection([
        ('customer', 'Customer Managed (FOB)'),
        ('donnamello', 'Donna Mello Managed (CFR/CIF)')
    ], string='Freight Management', 
       compute='_compute_freight_management',
       store=True)
    
    include_freight = fields.Boolean(
        'Include Freight in Service Invoice',
        compute='_compute_include_freight',
        store=True,
        readonly=False,
        tracking=True
    )
    
    freight_amount = fields.Monetary(
        'Freight Amount',
        currency_field='currency_id',
        tracking=True,
        help='Freight charges to be added ON TOP of service percentage'
    )
    
    include_insurance = fields.Boolean(
        'Include Insurance in Service Invoice',
        compute='_compute_include_insurance',
        store=True,
        readonly=False,
        tracking=True
    )
    
    insurance_amount = fields.Monetary(
        'Insurance Amount',
        currency_field='currency_id',
        tracking=True,
        help='Insurance charges to be added ON TOP of service percentage'
    )
    
    # Shipment tracking
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        compute='_compute_shipment_id',
        store=True
    )
    
    loading_confirmed = fields.Boolean(
        'Loading Confirmed',
        compute='_compute_loading_confirmed',
        store=True
    )
    
    # Invoice tracking
    product_invoice_id = fields.Many2one(
        'account.move',
        'Product Invoice',
        readonly=True,
        tracking=True,
        ondelete='restrict'
    )
    
    service_invoice_id = fields.Many2one(
        'account.move',
        'Service Invoice',
        readonly=True,
        tracking=True,
        ondelete='restrict'
    )
    
    # State
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('ready', 'Ready to Invoice'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled')
    ], string='State', default='draft', tracking=True, index=True)
    
    # Actual quantities from shipment
    actual_goods_value = fields.Monetary(
        'Actual Goods Value',
        currency_field='currency_id',
        compute='_compute_actual_amounts',
        store=True,
        help='Based on actual loaded quantities'
    )
    
    # Computed amounts for preview
    estimated_product_amount = fields.Monetary(
        'Product Invoice Amount',
        compute='_compute_estimated_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    estimated_service_amount = fields.Monetary(
        'Service Invoice Amount',
        compute='_compute_estimated_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    estimated_total_amount = fields.Monetary(
        'Total Invoice Amount',
        compute='_compute_estimated_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    # Downpayment allocation
    downpayment_total = fields.Monetary(
        'Total Downpayments',
        currency_field='currency_id',
        compute='_compute_downpayments',
        store=True
    )
    
    product_downpayment = fields.Monetary(
        'Product Invoice DP',
        currency_field='currency_id',
        compute='_compute_downpayments',
        store=True
    )
    
    service_downpayment = fields.Monetary(
        'Service Invoice DP',
        currency_field='currency_id',
        compute='_compute_downpayments',
        store=True
    )
    
    @api.depends('product_percentage')
    def _compute_service_percentage(self):
        """Calculate service percentage as remainder"""
        for config in self:
            config.service_percentage = 100.0 - config.product_percentage
    
    @api.depends('sale_incoterm_id')
    def _compute_freight_management(self):
        """Determine freight management based on Incoterm"""
        for config in self:
            if config.sale_incoterm_id:
                if config.sale_incoterm_id.code in ['FOB', 'FCA', 'EXW']:
                    config.freight_management = 'customer'
                else:
                    config.freight_management = 'donnamello'
            else:
                config.freight_management = False
    
    @api.depends('sale_incoterm_id')
    def _compute_include_freight(self):
        """Auto-set freight inclusion based on Incoterm"""
        for config in self:
            if config.sale_incoterm_id:
                # CFR and CIF include freight
                config.include_freight = config.sale_incoterm_id.code in ['CFR', 'CIF', 'CPT', 'CIP', 'DAP', 'DPU', 'DDP']
            else:
                config.include_freight = False
    
    @api.depends('sale_incoterm_id')
    def _compute_include_insurance(self):
        """Auto-set insurance inclusion based on Incoterm"""
        for config in self:
            if config.sale_incoterm_id:
                # Only CIF and CIP include insurance
                config.include_insurance = config.sale_incoterm_id.code in ['CIF', 'CIP']
            else:
                config.include_insurance = False
    
    def _compute_shipment_id(self):
        for config in self:
            # Safe check for shipment_ids field
            if config.deal_id:
                try:
                    # Check if field exists and is accessible
                    if hasattr(config.deal_id, 'shipment_ids') and config.deal_id.shipment_ids:
                        # ... existing code (keep whatever was here)
                        config.shipment_id = config.deal_id.shipment_ids[0] if config.deal_id.shipment_ids else False
                    else:
                        config.shipment_id = False
                except Exception as e:
                    _logger.debug(f"Could not access shipment_ids for deal {config.deal_id.name}: {e}")
                    config.shipment_id = False
            else:
                config.shipment_id = False
    
    @api.depends('shipment_id', 'shipment_id.state')
    def _compute_loading_confirmed(self):
        """Check if loading is confirmed"""
        for config in self:
            config.loading_confirmed = config.shipment_id and config.shipment_id.state in ['in_transit', 'delivered']
    
    @api.depends('shipment_id', 'shipment_id.state', 'deal_id', 'deal_id.total_sale_amount')
    def _compute_actual_amounts(self):
        """Calculate actual goods value based on loaded quantities
        
        REFACTORED v1.1.0: Module-independent pattern
        - Uses shipment line data if dm_shipment is installed and has lines
        - Falls back to deal amounts if shipment data unavailable
        - No hard dependency on shipment.line_ids field
        """
        for config in self:
            if config.shipment_id:
                # Try to get actual loaded quantities from shipment (if structure exists)
                actual_value = config._get_actual_value_from_shipment()
                
                if actual_value > 0:
                    config.actual_goods_value = actual_value
                else:
                    # Fallback: Use deal's total sale amount
                    config.actual_goods_value = config.deal_id.total_sale_amount or 0
            else:
                # No shipment yet: Use deal's total sale amount as estimate
                config.actual_goods_value = config.deal_id.total_sale_amount or 0
    
    def _get_actual_value_from_shipment(self):
        """Helper to safely extract actual loaded values from shipment
        
        Returns 0 if shipment structure doesn't exist or has no data.
        Uses hasattr() checks for module independence.
        """
        self.ensure_one()
        
        if not self.shipment_id:
            return 0
        
        # Check if shipment has line_ids field (dm_shipment may not be installed)
        if not hasattr(self.shipment_id, 'line_ids'):
            _logger.debug(
                f"Shipment {self.shipment_id.id} has no line_ids field - "
                f"dm_shipment module may not be installed"
            )
            return 0
        
        # Get lines for this deal
        actual_value = 0
        for line in self.shipment_id.line_ids:
            # Check each field exists before accessing
            if not hasattr(line, 'deal_id'):
                continue
            
            if line.deal_id != self.deal_id:
                continue
            
            if not hasattr(line, 'deal_line_id') or not line.deal_line_id:
                continue
            
            if not hasattr(line, 'actual_quantity_loaded'):
                continue
            
            if not hasattr(line.deal_line_id, 'price_packaging_sale'):
                continue
            
            # All fields exist - calculate
            actual_value += line.actual_quantity_loaded * line.deal_line_id.price_packaging_sale
        
        _logger.info(
            f"Extracted actual value ${actual_value:.2f} from shipment {self.shipment_id.id} "
            f"for deal {self.deal_id.name}"
        )
        
        return actual_value
    
    @api.depends('split_type', 'product_percentage', 'actual_goods_value',
                 'freight_amount', 'insurance_amount',
                 'include_freight', 'include_insurance')
    def _compute_estimated_amounts(self):
        """Calculate estimated split amounts for preview"""
        for config in self:
            # Update percentage based on split type
            if config.split_type == '80_20':
                config.product_percentage = 80.0
            elif config.split_type == '70_30':
                config.product_percentage = 70.0
            elif config.split_type == '90_10':
                config.product_percentage = 90.0
            # Custom keeps current value
            
            # Use actual goods value if available, otherwise use deal total
            goods_value = config.actual_goods_value or config.deal_id.total_value
            
            # Product invoice: percentage of goods value only
            config.estimated_product_amount = goods_value * (config.product_percentage / 100.0)
            
            # Service invoice: percentage of goods value PLUS freight/insurance
            service_base = goods_value * (config.service_percentage / 100.0)
            
            # Add freight and insurance ON TOP
            if config.include_freight:
                service_base += config.freight_amount
            if config.include_insurance:
                service_base += config.insurance_amount
            
            config.estimated_service_amount = service_base
            config.estimated_total_amount = config.estimated_product_amount + config.estimated_service_amount
    
    @api.depends('deal_id', 'estimated_product_amount', 'estimated_service_amount')
    def _compute_downpayments(self):
        """Calculate downpayment allocation"""
        for config in self:
            # Get paid downpayments
            dp_requests = self.env['dm.downpayment.request'].search([
                ('deal_id', '=', config.deal_id.id),
                ('request_type', '=', 'customer'),
                ('state', '=', 'paid')
            ])
            
            config.downpayment_total = sum(dp_requests.mapped('amount_received'))
            
            # Pro-rata allocation based on invoice amounts
            if config.estimated_total_amount > 0:
                product_ratio = config.estimated_product_amount / config.estimated_total_amount
                service_ratio = config.estimated_service_amount / config.estimated_total_amount
                
                config.product_downpayment = config.downpayment_total * product_ratio
                config.service_downpayment = config.downpayment_total * service_ratio
            else:
                config.product_downpayment = 0
                config.service_downpayment = 0
    
    @api.onchange('split_type')
    def _onchange_split_type(self):
        """Update percentages based on split type"""
        if self.split_type == '80_20':
            self.product_percentage = 80.0
        elif self.split_type == '70_30':
            self.product_percentage = 70.0
        elif self.split_type == '90_10':
            self.product_percentage = 90.0
        # Custom keeps current values
    
    @api.constrains('product_percentage')
    def _check_product_percentage(self):
        """Validate percentage is valid"""
        for config in self:
            if config.product_percentage < 0 or config.product_percentage > 100:
                raise ValidationError(_('Product percentage must be between 0 and 100.'))
    
    @api.constrains('state', 'product_invoice_id', 'service_invoice_id')
    def _check_invoice_state(self):
        """Validate invoice state consistency"""
        for config in self:
            if config.state == 'invoiced' and not (config.product_invoice_id and config.service_invoice_id):
                raise ValidationError(_('Cannot mark as invoiced without both invoices generated.'))
    
    def action_confirm(self):
        """Confirm split configuration"""
        for config in self:
            if config.state != 'draft':
                raise UserError(_('Only draft configurations can be confirmed.'))
            
            # Validate Incoterm-based requirements
            if config.sale_incoterm_id:
                if config.sale_incoterm_id.code in ['CFR', 'CIF'] and not config.freight_amount:
                    raise UserError(_('Freight amount is required for %s terms.') % config.sale_incoterm_id.code)
                if config.sale_incoterm_id.code == 'CIF' and not config.insurance_amount:
                    raise UserError(_('Insurance amount is required for CIF terms.'))
            
            config.state = 'confirmed'
    
    def action_mark_ready(self):
        """Mark as ready to invoice (after loading confirmation)"""
        for config in self:
            if config.state != 'confirmed':
                raise UserError(_('Only confirmed configurations can be marked ready.'))
            
            if not config.loading_confirmed:
                raise UserError(_('Cannot mark ready - loading not confirmed.'))
            
            if not config.actual_goods_value:
                raise UserError(_('Cannot mark ready - no actual quantities from shipment.'))
            
            config.state = 'ready'
    
    def action_generate_invoices(self):
        """Open wizard to generate split invoices"""
        self.ensure_one()
        
        if self.state == 'invoiced':
            raise UserError(_('Invoices already generated for this configuration.'))
        
        if not self.loading_confirmed:
            raise UserError(_('Cannot generate invoices - loading not confirmed.'))
        
        # Prepare invoice data
        invoice_data = self.prepare_invoices()
        
        # Open wizard for review and generation
        wizard = self.env['dm.invoice.generation.wizard'].create({
            'split_config_id': self.id,
            'deal_id': self.deal_id.id,
            'generate_split': True,
            'product_amount': invoice_data['product_invoice']['amount_total'],
            'product_dp': invoice_data['product_invoice']['amount_dp'],
            'product_due': invoice_data['product_invoice']['amount_due'],
            'service_amount': invoice_data['service_invoice']['amount_total'],
            'service_dp': invoice_data['service_invoice']['amount_dp'],
            'service_due': invoice_data['service_invoice']['amount_due'],
            'freight_amount': invoice_data['service_invoice']['components']['freight'],
            'insurance_amount': invoice_data['service_invoice']['components']['insurance'],
        })
        
        # Add line details
        for line_data in invoice_data['product_invoice']['lines']:
            self.env['dm.invoice.generation.wizard.line'].create({
                'wizard_id': wizard.id,
                'product_id': line_data['product_id'],
                'quantity': line_data['quantity'],
                'price_unit': line_data['price_unit'],
            })
        
        return {
            'name': _('Generate Split Invoices'),
            'type': 'ir.actions.act_window',
            'res_model': 'dm.invoice.generation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_split_config_id': self.id}
        }
    
    def prepare_invoices(self):
        """
        Prepare product and service invoices based on ACTUAL shipped quantities.
        Service invoice = service% of goods value PLUS freight/insurance.
        
        REFACTORED v1.1.0: Safe shipment access with fallback
        
        Returns dict with invoice details.
        """
        self.ensure_one()
        
        if not self.shipment_id:
            raise UserError(_('No shipment found for this deal.'))
        
        # Check if shipment has line structure
        if not hasattr(self.shipment_id, 'line_ids'):
            raise UserError(_(
                'Shipment does not have line data. '
                'Invoice generation requires dm_shipment module to be installed and shipment to have lines.'
            ))
        
        # Get ACTUAL shipped quantities from shipment lines
        shipped_lines = self.shipment_id.line_ids.filtered(
            lambda l: hasattr(l, 'deal_id') and l.deal_id == self.deal_id
        )
        
        if not shipped_lines:
            raise UserError(_('No shipped lines found for this deal.'))
        
        # Calculate actual goods value based on loaded quantities
        product_lines = []
        goods_total = 0.0
        
        for line in shipped_lines:
            # Verify line has required fields
            if not hasattr(line, 'deal_line_id') or not line.deal_line_id:
                continue
            
            if not hasattr(line, 'actual_quantity_loaded'):
                _logger.warning(
                    f"Shipment line {line.id} missing actual_quantity_loaded field"
                )
                continue
            
            if not hasattr(line.deal_line_id, 'price_packaging_sale'):
                continue
            
            # Use ACTUAL loaded quantity, not ordered
            line_total = line.actual_quantity_loaded * line.deal_line_id.price_packaging_sale
            goods_total += line_total
            
            product_lines.append({
                'product_id': line.deal_line_id.product_id.id,
                'quantity': line.actual_quantity_loaded,
                'price_unit': line.deal_line_id.price_packaging_sale,
                'subtotal': line_total,
                'deal_line_id': line.deal_line_id.id,
            })
        
        # Calculate split amounts
        product_amount = goods_total * (self.product_percentage / 100.0)
        service_base = goods_total * (self.service_percentage / 100.0)
        
        # Service components (ON TOP of percentage)
        service_components = {
            'base': service_base,  # The percentage portion
            'freight': self.freight_amount if self.include_freight else 0.0,
            'insurance': self.insurance_amount if self.include_insurance else 0.0,
        }
        service_total = sum(service_components.values())
        
        # Get downpayments to apply
        dp_requests = self.env['dm.downpayment.request'].search([
            ('deal_id', '=', self.deal_id.id),
            ('request_type', '=', 'customer'),
            ('state', '=', 'paid')
        ])
        total_dp = sum(dp_requests.mapped('amount_received'))
        
        # Calculate pro-rata downpayment application
        total_invoice = product_amount + service_total
        
        if total_invoice > 0:
            product_dp = total_dp * (product_amount / total_invoice)
            service_dp = total_dp * (service_total / total_invoice)
        else:
            product_dp = service_dp = 0.0
        
        result = {
            'product_invoice': {
                'amount_total': product_amount,
                'amount_dp': product_dp,
                'amount_due': product_amount - product_dp,
                'lines': product_lines,
                'percentage': self.product_percentage,
            },
            'service_invoice': {
                'amount_total': service_total,
                'amount_dp': service_dp,
                'amount_due': service_total - service_dp,
                'components': service_components,
                'percentage': self.service_percentage,
            },
            'downpayments': dp_requests,
            'total_dp': total_dp,
            'goods_value': goods_total,
        }
        
        return result
    
    def action_view_product_invoice(self):
        """View product invoice"""
        self.ensure_one()
        if not self.product_invoice_id:
            raise UserError(_('No product invoice generated yet.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.product_invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_view_service_invoice(self):
        """View service invoice"""
        self.ensure_one()
        if not self.service_invoice_id:
            raise UserError(_('No service invoice generated yet.'))
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'res_id': self.service_invoice_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
    
    def action_cancel(self):
        """Cancel split configuration"""
        for config in self:
            if config.state == 'invoiced':
                raise UserError(_('Cannot cancel - invoices already generated.'))
            
            config.state = 'cancelled'
    
    def action_reset_draft(self):
        """Reset to draft"""
        for config in self:
            if config.state == 'invoiced':
                raise UserError(_('Cannot reset - invoices already generated.'))
            
            config.state = 'draft'
    
    @api.model
    def create_from_deal(self, deal):
        """Create split configuration from deal when confirmed"""
        # Check if already exists
        existing = self.search([('deal_id', '=', deal.id)], limit=1)
        if existing:
            return existing
        
        # Determine split type from deal
        split_type = 'custom'
        if deal.invoice_split == '80_20':
            split_type = '80_20'
        elif deal.invoice_split == '70_30':
            split_type = '70_30'
        
        # Create configuration
        config = self.create({
            'deal_id': deal.id,
            'split_type': split_type,
            'freight_amount': 0.0,  # To be updated based on actual quotes
            'insurance_amount': 0.0,  # To be updated based on actual policy
        })
        
        _logger.info(f"Created invoice split config for deal {deal.name}")
        
        return config
    
    def update_freight_insurance(self, freight=None, insurance=None):
        """Update freight and insurance amounts (called when quotes received)"""
        self.ensure_one()
        
        if self.state == 'invoiced':
            raise UserError(_('Cannot update amounts - invoices already generated.'))
        
        vals = {}
        if freight is not None:
            vals['freight_amount'] = freight
        if insurance is not None:
            vals['insurance_amount'] = insurance
        
        self.write(vals)
        
        self.message_post(
            body=_('Updated charges: Freight=%s, Insurance=%s') % (freight or 'unchanged', insurance or 'unchanged')
        )
        
        return True