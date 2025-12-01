# -*- coding: utf-8 -*-
from odoo import api, fields, models
import logging

_logger = logging.getLogger(__name__)


class PurchaseOrder(models.Model):
    """
    DonnaMello Purchase Order Extensions
    
    Phase 0: Added subdeal reference.
    Package-Native: Order totals calculated from package qty × package price.
    
    PO now links to BOTH:
    - dm_deal_id: For reporting and historical tracking
    - dm_subdeal_id: For execution workflow
    """
    _inherit = 'purchase.order'
    
    dm_deal_id = fields.Many2one(
        'dm.deal',
        string='DM Deal',
        readonly=True,
        index=True,
        help='Reference to originating DonnaMello deal'
    )
    
    dm_subdeal_id = fields.Many2one(
        'dm.deal.subdeal',
        string='DM Sub-Deal',
        readonly=True,
        index=True,
        help='Reference to originating sub-deal (execution layer)'
    )
    
    is_dm_order = fields.Boolean(
        string='Is DM Order',
        compute='_compute_is_dm_order',
        store=True,
        help='True if this order originated from a DM deal'
    )
    
    @api.depends('dm_deal_id')
    def _compute_is_dm_order(self):
        """Determine if order is from DM deal"""
        for order in self:
            order.is_dm_order = bool(order.dm_deal_id)
    
    # =========================================================================
    # OVERRIDE: Order Totals for Package-Native Calculation
    # =========================================================================
    
    def _get_dm_package_native_totals(self):
        """
        Calculate package-native totals for DM orders.
        
        Returns:
            tuple: (amount_untaxed, amount_tax, amount_total)
        """
        self.ensure_one()
        amount_untaxed = 0.0
        amount_tax = 0.0
        
        for line in self.order_line.filtered(lambda x: not x.display_type):
            if line.is_dm_line and line.packaging_qty_dm and line.packaging_price_unit:
                # Package-native: qty × price (6-decimal precision preserved)
                line_subtotal = line.packaging_qty_dm * line.packaging_price_unit
                amount_untaxed += line_subtotal
                amount_tax += line.price_tax
            else:
                # Standard line
                amount_untaxed += line.price_subtotal
                amount_tax += line.price_tax
        
        return amount_untaxed, amount_tax, amount_untaxed + amount_tax
    
    @api.depends('order_line.price_subtotal', 'order_line.price_tax', 
                 'order_line.price_total', 'order_line.is_dm_line',
                 'order_line.packaging_qty_dm', 'order_line.packaging_price_unit')
    def _compute_amounts(self):
        """
        Override to use package-native amounts for DM orders.
        
        For DM orders: Sum of (packaging_qty_dm × packaging_price_unit) per line
        For regular orders: Standard Odoo calculation
        """
        for order in self:
            if order.is_dm_order or any(line.is_dm_line for line in order.order_line):
                amount_untaxed, amount_tax, amount_total = order._get_dm_package_native_totals()
                
                order.amount_untaxed = order.currency_id.round(amount_untaxed)
                order.amount_tax = order.currency_id.round(amount_tax)
                order.amount_total = order.amount_untaxed + order.amount_tax
                
                _logger.debug(
                    f"PO {order.name}: Package-native totals - "
                    f"Untaxed: {order.amount_untaxed}, Total: {order.amount_total}"
                )
            else:
                super(PurchaseOrder, order)._compute_amounts()
    
    @api.depends('order_line.taxes_id', 'order_line.price_subtotal', 'amount_total', 'amount_untaxed',
                 'order_line.is_dm_line', 'order_line.packaging_qty_dm', 'order_line.packaging_price_unit')
    def _compute_tax_totals(self):
        """
        Override to use package-native amounts in tax_totals display for DM orders.
        
        The tax_totals field is what the form view actually displays via the
        account-tax-totals-field widget. We must override this to show correct totals.
        """
        # First let Odoo compute standard tax_totals
        super()._compute_tax_totals()
        
        # Then override for DM orders
        for order in self:
            if order.is_dm_order or any(line.is_dm_line for line in order.order_line):
                amount_untaxed, amount_tax, amount_total = order._get_dm_package_native_totals()
                
                # Round to currency precision
                amount_untaxed = order.currency_id.round(amount_untaxed)
                amount_tax = order.currency_id.round(amount_tax)
                amount_total = order.currency_id.round(amount_total)
                
                # Update the tax_totals dict with package-native values
                if order.tax_totals:
                    # Get existing tax_totals and update amounts
                    updated_totals = dict(order.tax_totals)
                    updated_totals.update({
                        'amount_untaxed': amount_untaxed,
                        'amount_total': amount_total,
                        'formatted_amount_total': f"{order.currency_id.symbol} {amount_total:,.2f}",
                        'formatted_amount_untaxed': f"{order.currency_id.symbol} {amount_untaxed:,.2f}",
                    })
                    order.tax_totals = updated_totals
                    
                    _logger.debug(
                        f"PO {order.name}: Updated tax_totals with package-native - "
                        f"Untaxed: {amount_untaxed}, Total: {amount_total}"
                    )


class PurchaseOrderLine(models.Model):
    """
    DonnaMello Purchase Order Line Extensions
    
    Package-Native Architecture:
    - packaging_qty_dm: Quantity in packages ORDERED (SOURCE OF TRUTH)
    - packaging_price_unit: Price per package with 6-decimal precision (SOURCE OF TRUTH)
    - qty_received_packages: Quantity in packages ACTUALLY RECEIVED (from deal line)
    - Standard Odoo fields (product_qty, price_unit) derived for compatibility
    """
    _inherit = 'purchase.order.line'
    
    dm_deal_line_id = fields.Many2one(
        'dm.deal.line',
        string='Deal Line',
        readonly=True,
        index=True,
        help='Reference to originating deal line'
    )
    
    # =========================================================================
    # PACKAGE-NATIVE FIELDS (Source of Truth for DM Deals)
    # =========================================================================
    
    packaging_qty_dm = fields.Float(
        string='Ordered (Pkg)',
        digits=(16, 3),
        readonly=True,
        help='Package quantity ORDERED from deal - SOURCE OF TRUTH for DM deals'
    )
    
    packaging_price_unit = fields.Float(
        string='Pkg Price',
        digits=(16, 6),
        readonly=True,
        help='Price per package with 6-decimal precision - SOURCE OF TRUTH for DM deals'
    )
    
    qty_received_packages = fields.Float(
        string='Received (Pkg)',
        digits=(16, 3),
        readonly=True,
        help='Received quantity in packages - populated from deal line quantity_loaded'
    )
    
    is_dm_line = fields.Boolean(
        string='Is DM Line',
        compute='_compute_is_dm_line',
        store=True,
        help='True if this line originated from a DM deal'
    )
    
    amount_package_native = fields.Monetary(
        string='Pkg Amount',
        compute='_compute_amount_package_native',
        store=True,
        currency_field='currency_id',
        help='Subtotal calculated from package qty × package price (no rounding errors)'
    )
    
    @api.depends('dm_deal_line_id')
    def _compute_is_dm_line(self):
        """Determine if line is from DM deal"""
        for line in self:
            line.is_dm_line = bool(line.dm_deal_line_id)
    
    @api.depends('packaging_qty_dm', 'packaging_price_unit', 'is_dm_line')
    def _compute_amount_package_native(self):
        """Calculate package-native amount for DM lines"""
        for line in self:
            if line.is_dm_line and line.packaging_qty_dm and line.packaging_price_unit:
                line.amount_package_native = line.packaging_qty_dm * line.packaging_price_unit
            else:
                line.amount_package_native = 0.0
    
    # =========================================================================
    # OVERRIDE: Line Amount Calculation for Package-Native Precision
    # =========================================================================
    
    @api.depends('product_qty', 'price_unit', 'taxes_id',
                 'is_dm_line', 'packaging_qty_dm', 'packaging_price_unit')
    def _compute_amount(self):
        """
        Override to use package-native calculation for DM lines.
        """
        super()._compute_amount()
        
        for line in self:
            if line.is_dm_line and line.packaging_qty_dm and line.packaging_price_unit:
                # Package-native subtotal
                subtotal = line.packaging_qty_dm * line.packaging_price_unit
                
                # Calculate taxes on package-native amount
                taxes = line.taxes_id.compute_all(
                    line.packaging_price_unit,
                    line.order_id.currency_id,
                    line.packaging_qty_dm,
                    product=line.product_id,
                    partner=line.order_id.partner_id
                )
                
                line.update({
                    'price_tax': sum(t.get('amount', 0.0) for t in taxes.get('taxes', [])),
                    'price_total': taxes['total_included'],
                    'price_subtotal': taxes['total_excluded'],
                })
    
    # =========================================================================
    # METHODS FOR BILL CREATION
    # =========================================================================
    
    def _prepare_account_move_line(self, move=False):
        """
        Pass package-native values to bill line.
        
        Uses qty_received_packages (actual received) for billing,
        falls back to packaging_qty_dm (ordered) if not yet received.
        """
        res = super()._prepare_account_move_line(move=move)
        
        if self.is_dm_line:
            # Use actual received packages for billing (Option B)
            actual_packages = self.qty_received_packages or self.packaging_qty_dm
            res.update({
                'packaging_qty_dm': actual_packages,
                'packaging_price_unit': self.packaging_price_unit,
                'dm_deal_line_id': self.dm_deal_line_id.id,
            })
        
        return res