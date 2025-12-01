# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
from datetime import timedelta
import logging

_logger = logging.getLogger(__name__)


class DmDealSubdeal(models.Model):
    """
    Deal Sub-Deal - Execution Layer
    
    Phase 0: 1:1 relationship with deal (single subdeal per deal)
    Phase 1: Enable 1:N for split scenarios
    
    Encapsulates:
    - Deal lines (moved from dm.deal)
    - SO/PO documents (moved from dm.deal)
    - Milestones (moved from dm.deal)
    - Shipment allocation (moved from dm.deal)
    - State machine (execution lifecycle)
    """
    _name = 'dm.deal.subdeal'
    _description = 'Deal Sub-Deal (Execution)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'deal_id, sequence, id'
    
    # =========================================================================
    # HEADER
    # =========================================================================
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Deal',
        required=True,
        ondelete='cascade',
        index=True
    )
    
    name = fields.Char(
        string='Name',
        default='Shipment',
        required=True
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10
    )
    
    # Inherited context (for convenience)
    customer_id = fields.Many2one(
        'res.partner',
        related='deal_id.customer_id',
        string='Customer',
        store=True,
        readonly=True
    )
    
    supplier_id = fields.Many2one(
        'res.partner',
        related='deal_id.supplier_id',
        string='Supplier',
        store=True,
        readonly=True
    )
    
    customer_po_number = fields.Char(
        related='deal_id.customer_po_number',
        string='Customer PO',
        store=True,
        readonly=True
    )
    
    currency_id = fields.Many2one(
        'res.currency',
        related='deal_id.currency_id',
        string='Currency',
        store=True,
        readonly=True
    )
    
    # =========================================================================
    # LINES (Moved from dm.deal)
    # =========================================================================
    
    line_ids = fields.One2many(
        'dm.deal.line',
        'subdeal_id',
        string='Lines',
        copy=True
    )
    
    # =========================================================================
    # DOCUMENTS (Moved from dm.deal)
    # =========================================================================
    
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Sales Order',
        readonly=True,
        index=True
    )
    
    purchase_order_id = fields.Many2one(
        'purchase.order',
        string='Purchase Order',
        readonly=True,
        index=True
    )
    
    # =========================================================================
    # SHIPMENT ALLOCATION (Moved from dm.deal)
    # =========================================================================
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        readonly=True,
        index=True
    )
    
    shipment_allocated = fields.Boolean(
        string='Allocated to Shipment',
        default=False,
        readonly=True,
        index=True
    )
    
    # =========================================================================
    # STATE MACHINE (Execution Lifecycle)
    # =========================================================================
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('in_production', 'In Production'),
        ('ready', 'Ready to Ship'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ], string='Status',
        default='draft',
        required=True,
        tracking=True
    )
    
    # =========================================================================
    # MILESTONES (Moved from dm_deal_milestones.py)
    # =========================================================================
    
    # Production Start
    production_start_requested = fields.Date(string='Prod Start (Requested)')
    production_start_current = fields.Date(string='Prod Start (Current)')
    production_start_actual = fields.Date(string='Prod Start (Actual)')
    
    # Ready to Ship (RTS)
    rts_requested = fields.Date(string='RTS (Requested)')
    rts_current = fields.Date(string='RTS (Current)')
    rts_actual = fields.Date(string='RTS (Actual)')
    
    # Loading
    loading_requested = fields.Date(string='Loading (Requested)')
    loading_current = fields.Date(string='Loading (Current)')
    loading_actual = fields.Date(string='Loading (Actual)')
    
    # ETD (Departure)
    etd_requested = fields.Date(string='ETD (Requested)')
    etd_current = fields.Date(string='ETD (Current)')
    etd_actual = fields.Date(string='ETD (Actual)')
    
    # ETA (Arrival)
    eta_requested = fields.Date(string='ETA (Requested)')
    eta_current = fields.Date(string='ETA (Current)')
    eta_actual = fields.Date(string='ETA (Actual)')
    
    # Delivery
    delivery_requested = fields.Date(string='Delivery (Requested)')
    delivery_current = fields.Date(string='Delivery (Current)')
    delivery_actual = fields.Date(string='Delivery (Actual)')
    
    # Calculated production start (from RTS with lead time)
    production_start_calculated = fields.Date(
        string='Prod Start (Calculated)',
        compute='_compute_production_start_calculated',
        store=True
    )
    
    @api.depends('rts_current', 'rts_requested', 'line_ids.product_id')
    def _compute_production_start_calculated(self):
        """Calculate production start from RTS minus product lead time"""
        for subdeal in self:
            rts_date = subdeal.rts_current or subdeal.rts_requested
            
            if rts_date:
                # Get max production cycle from products, fallback to 21 days
                max_cycle = 21
                for line in subdeal.line_ids:
                    if hasattr(line.product_id, 'total_production_cycle') and line.product_id.total_production_cycle:
                        max_cycle = max(max_cycle, line.product_id.total_production_cycle)
                
                subdeal.production_start_calculated = rts_date - timedelta(days=max_cycle)
            else:
                subdeal.production_start_calculated = False
    
    # =========================================================================
    # AMOUNTS (Computed from lines)
    # =========================================================================
    
    amount_untaxed_sale = fields.Monetary(
        string='Sale Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    amount_untaxed_purchase = fields.Monetary(
        string='Purchase Amount',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    margin_amount = fields.Monetary(
        string='Margin',
        compute='_compute_amounts',
        store=True,
        currency_field='currency_id'
    )
    
    margin_percent = fields.Float(
        string='Margin %',
        compute='_compute_amounts',
        store=True,
        digits=(5, 2)
    )
    
    @api.depends('line_ids.amount_sale', 'line_ids.amount_purchase')
    def _compute_amounts(self):
        """Compute totals from lines"""
        for subdeal in self:
            subdeal.amount_untaxed_sale = sum(subdeal.line_ids.mapped('amount_sale'))
            subdeal.amount_untaxed_purchase = sum(subdeal.line_ids.mapped('amount_purchase'))
            subdeal.margin_amount = subdeal.amount_untaxed_sale - subdeal.amount_untaxed_purchase
            
            if subdeal.amount_untaxed_sale > 0:
                subdeal.margin_percent = (subdeal.margin_amount / subdeal.amount_untaxed_sale) * 100
            else:
                subdeal.margin_percent = 0.0
    
    # =========================================================================
    # WORKFLOW METHODS
    # =========================================================================
    
    def action_confirm(self):
        """Confirm subdeal"""
        for subdeal in self:
            if not subdeal.line_ids:
                raise UserError(_('Cannot confirm subdeal without lines'))
            
            subdeal.write({'state': 'confirmed'})
            _logger.info(f"Sub-deal {subdeal.id} confirmed for deal {subdeal.deal_id.name}")
    
    def action_start_production(self):
        """Start production"""
        for subdeal in self:
            subdeal.write({
                'state': 'in_production',
                'production_start_actual': fields.Date.today()
            })
    
    def action_mark_ready(self):
        """Mark ready to ship"""
        for subdeal in self:
            subdeal.write({
                'state': 'ready',
                'rts_actual': fields.Date.today()
            })
    
    def action_mark_shipped(self):
        """Mark shipped - cascades to parent deal"""
        for subdeal in self:
            subdeal.write({
                'state': 'shipped',
                'loading_actual': fields.Date.today()
            })
            
            # CASCADE to deal
            deal_vals = {'state': 'shipped'}
            if not subdeal.deal_id.loading_actual:
                deal_vals['loading_actual'] = fields.Date.today()
            
            subdeal.deal_id.with_context(
                skip_milestone_warnings=True,
                from_subdeal_cascade=True
            ).write(deal_vals)
            
            _logger.info(
                f"Subdeal {subdeal.id}: Marked shipped, cascaded to deal {subdeal.deal_id.name}"
            )
    
    def action_mark_delivered(self):
        """Mark delivered - cascades to parent deal"""
        for subdeal in self:
            subdeal.write({
                'state': 'delivered',
                'delivery_actual': fields.Date.today()
            })
            
            # CASCADE to deal
            deal_vals = {'state': 'delivered'}
            if not subdeal.deal_id.delivery_actual:
                deal_vals['delivery_actual'] = fields.Date.today()
            
            subdeal.deal_id.with_context(
                skip_milestone_warnings=True,
                from_subdeal_cascade=True
            ).write(deal_vals)
            
            _logger.info(
                f"Subdeal {subdeal.id}: Marked delivered, cascaded to deal {subdeal.deal_id.name}"
            )
    
    def action_cancel(self):
        """Cancel subdeal"""
        for subdeal in self:
            if subdeal.shipment_allocated:
                raise UserError(_(
                    'Cannot cancel subdeal allocated to shipment.\n'
                    'Remove from shipment first.'
                ))
            
            subdeal.write({'state': 'cancelled'})

    def write(self, vals):
        """Override write to cascade milestone actuals to parent deal"""
        res = super().write(vals)
        
        # Skip cascade if coming from deal (prevent loops)
        if self.env.context.get('from_deal_cascade'):
            return res
        
        # Milestone fields that should cascade to deal
        MILESTONE_CASCADE = {
            'loading_actual': 'loading_actual',
            'etd_actual': 'etd_actual',
            'eta_actual': 'eta_actual',
            'delivery_actual': 'delivery_actual',
        }
        
        # Check if any milestone actual was updated
        cascade_vals = {}
        for subdeal_field, deal_field in MILESTONE_CASCADE.items():
            if subdeal_field in vals and vals[subdeal_field]:
                cascade_vals[deal_field] = vals[subdeal_field]
        
        # Cascade to deal if needed
        if cascade_vals:
            for subdeal in self:
                # Only cascade if deal doesn't already have the value
                deal_update = {}
                for field, value in cascade_vals.items():
                    if not subdeal.deal_id[field]:
                        deal_update[field] = value
                
                if deal_update:
                    subdeal.deal_id.with_context(
                        skip_milestone_warnings=True,
                        from_subdeal_cascade=True
                    ).write(deal_update)
                    
                    _logger.info(
                        f"Subdeal {subdeal.id}: Cascaded milestones to deal {subdeal.deal_id.name}: "
                        f"{list(deal_update.keys())}"
                    )
        
        return res
    
    # =========================================================================
    # STOCK FINALIZATION (Called by dm_shipment on loading complete)
    # =========================================================================

    def action_finalize_shipment(self):
        """
        Public entry point called by dm_shipment on loading complete.
        
        Finalizes both SO delivery and PO receipt for this subdeal.
        """
        self.ensure_one()
        
        delivery_ok = self._finalize_delivery()
        receipt_ok = self._finalize_receipt()
        
        _logger.info(
            f"Subdeal {self.id}: Finalize shipment complete - "
            f"delivery={'OK' if delivery_ok else 'SKIP'}, "
            f"receipt={'OK' if receipt_ok else 'SKIP'}"
        )
        
        return delivery_ok or receipt_ok
    
    def _populate_stock_move_dm_fields(self, picking):
        """
        Populate package-native fields on stock moves after picking validation.
        
        Uses actual quantity_loaded from deal lines (not ordered qty).
        """
        for move in picking.move_ids:
            sol = move.sale_line_id
            pol = move.purchase_line_id
            
            # Find matching deal line
            deal_line = None
            price_field = None
            
            if sol and hasattr(sol, 'dm_deal_line_id') and sol.dm_deal_line_id:
                deal_line = sol.dm_deal_line_id
                price_field = 'price_packaging_sale'
            elif pol and hasattr(pol, 'dm_deal_line_id') and pol.dm_deal_line_id:
                deal_line = pol.dm_deal_line_id
                price_field = 'price_packaging_purchase'
            
            if deal_line:
                # Use quantity_loaded (actual shipped), not ordered qty
                actual_packages = deal_line.quantity_loaded or 0.0
                package_price = getattr(deal_line, price_field, 0.0) if price_field else 0.0
                
                move.write({
                    'dm_deal_line_id': deal_line.id,
                    'packaging_qty_dm': actual_packages,
                    'packaging_price_unit': package_price,
                })
                _logger.debug(
                    f"Stock move {move.id}: Populated DM fields - "
                    f"pkg_qty={actual_packages} (loaded), pkg_price={package_price}"
                )
    
    def _convert_packages_to_units(self, line):
        """
        Convert package quantity to units for stock move.
        
        Args:
            line: dm.deal.line record
            
        Returns:
            float: Quantity in product UoM (units)
        """
        if not line.quantity_loaded:
            return 0.0
        
        # Get units per package from product packaging
        units_per_package = 1.0
        if line.product_packaging_id and line.product_packaging_id.qty:
            units_per_package = line.product_packaging_id.qty
        elif hasattr(line, 'units_per_package') and line.units_per_package:
            units_per_package = line.units_per_package
        
        units = line.quantity_loaded * units_per_package
        
        _logger.debug(
            f"Package→Unit conversion: {line.quantity_loaded} packages × "
            f"{units_per_package} = {units} units"
        )
        
        return units
    
    def _update_so_line_delivered_packages(self):
        """
        Populate qty_delivered_packages on SO lines from deal line quantity_loaded.
        """
        self.ensure_one()
        
        # Debug via chatter
        self.deal_id.message_post(body="🔧 _update_so_line_delivered_packages START")
        
        if not self.sale_order_id:
            self.deal_id.message_post(body="🔧 No sale_order_id - returning")
            return
        
        self.deal_id.message_post(body=f"🔧 Processing SO: {self.sale_order_id.name}")
        
        dm_lines = self.sale_order_id.order_line.filtered(
            lambda l: hasattr(l, 'is_dm_line') and l.is_dm_line
        )
        self.deal_id.message_post(body=f"🔧 Found {len(dm_lines)} DM lines")
        
        for so_line in dm_lines:
            deal_line = so_line.dm_deal_line_id
            qty_loaded = deal_line.quantity_loaded if deal_line else None
            
            self.deal_id.message_post(
                body=f"🔧 SO line {so_line.id}: deal_line={deal_line.id if deal_line else None}, qty_loaded={qty_loaded}"
            )
            
            if deal_line and deal_line.quantity_loaded:
                so_line.write({
                    'qty_delivered_packages': deal_line.quantity_loaded,
                })
                self.deal_id.message_post(
                    body=f"✅ Wrote qty_delivered_packages={deal_line.quantity_loaded} to SO line {so_line.id}"
                )
            else:
                self.deal_id.message_post(
                    body=f"❌ Condition failed for SO line {so_line.id}"
                )
        
        self.deal_id.message_post(body="🔧 _update_so_line_delivered_packages END")
    
    def _update_po_line_received_packages(self):
        """
        Populate qty_received_packages on PO lines from deal line quantity_loaded.
        
        Called after receipt finalization to ensure PO lines carry
        actual received packages for bill creation.
        """
        self.ensure_one()
        
        if not self.purchase_order_id:
            return
        
        for po_line in self.purchase_order_id.order_line.filtered(
            lambda l: hasattr(l, 'is_dm_line') and l.is_dm_line
        ):
            deal_line = po_line.dm_deal_line_id
            if deal_line and deal_line.quantity_loaded:
                po_line.write({
                    'qty_received_packages': deal_line.quantity_loaded,
                })
                _logger.debug(
                    f"PO line {po_line.id}: Set qty_received_packages={deal_line.quantity_loaded} "
                    f"from deal line {deal_line.id}"
                )
    
    def _finalize_delivery(self):
        """
        Update SO delivery with loaded quantities and validate.
        
        Flow:
        1. Find pending delivery (outgoing picking not done/cancelled)
        2. Convert package quantities to units for stock moves
        3. Update move.quantity with converted units
        4. Validate picking (skip backorder dialog)
        5. Populate DM fields on stock moves for invoice chain
        6. Update SO lines with qty_delivered_packages from deal
        7. Odoo auto-syncs SO.line.qty_delivered (in units)
        
        Returns:
            bool: True if successful, False otherwise
        """
        self.ensure_one()
        
        if not self.sale_order_id:
            _logger.warning(f"Subdeal {self.id}: No SO linked for delivery finalization")
            return False
        
        # Chatter: Debug pickings
        picking_info = [(p.name, p.state, p.picking_type_id.code) for p in self.sale_order_id.picking_ids]
        self.deal_id.message_post(
            body=_('🔍 SO Pickings found: %s') % str(picking_info)
        )
        
        # Find pending outgoing picking
        delivery = self.sale_order_id.picking_ids.filtered(
            lambda p: p.state not in ['done', 'cancel']
            and p.picking_type_id.code == 'outgoing'
        )[:1]
        
        if not delivery:
            _logger.warning(
                f"Subdeal {self.id}: No pending delivery found for SO {self.sale_order_id.name}. "
                f"Picking states: {self.sale_order_id.picking_ids.mapped('state')}"
            )
            self.deal_id.message_post(
                body=_('⚠️ No pending outgoing delivery found for SO %s') % self.sale_order_id.name
            )
            return False
        
        # Chatter: Selected picking
        self.deal_id.message_post(
            body=_('🔍 Processing delivery: %s (state: %s)') % (delivery.name, delivery.state)
        )
        
        try:
            # Update quantities from subdeal lines
            moves_updated = 0
            move_details = []
            for move in delivery.move_ids:
                # Find matching subdeal line by product
                line = self.line_ids.filtered(
                    lambda l: l.product_id.id == move.product_id.id
                )[:1]
                
                if line:
                    if line.quantity_loaded and line.quantity_loaded > 0:
                        # Convert packages to units for stock system
                        units_qty = self._convert_packages_to_units(line)
                        move.quantity = units_qty
                        moves_updated += 1
                        move_details.append(
                            f"{move.product_id.name}: {line.quantity_loaded} pkg → {units_qty} units"
                        )
                        _logger.debug(
                            f"Delivery move {move.id}: Set quantity={units_qty} "
                            f"({line.quantity_loaded} packages) for {move.product_id.name}"
                        )
                    else:
                        move.quantity = 0
                        move_details.append(f"{move.product_id.name}: 0 (not loaded)")
                else:
                    _logger.warning(
                        f"Delivery move {move.id}: No matching subdeal line for {move.product_id.name}"
                    )
                    move.quantity = 0
                    move_details.append(f"{move.product_id.name}: 0 (no matching line)")
            
            # Chatter: Move updates
            self.deal_id.message_post(
                body=_('📦 Delivery moves updated:<br/>%s') % '<br/>'.join(move_details)
            )
            
            # Validate picking
            delivery.with_context(
                skip_backorder=True,
                cancel_backorder=True,
                skip_sms=True,
                skip_immediate=True
            ).button_validate()
            
            # Populate DM fields on validated moves for invoice chain
            self._populate_stock_move_dm_fields(delivery)
            
            # Update SO lines with delivered packages from deal
            self._update_so_line_delivered_packages()
            
            _logger.info(
                f"Subdeal {self.id}: Finalized delivery {delivery.name} "
                f"({moves_updated} moves updated, state={delivery.state})"
            )
            
            # Chatter: Validation result
            self.deal_id.message_post(
                body=_('✅ Delivery %s validated (state: %s)') % (delivery.name, delivery.state)
            )
            
            # Post message to SO
            self.sale_order_id.message_post(
                body=_(
                    'Delivery <b>%s</b> finalized from shipment loading.<br/>'
                    'Quantities updated from actual loaded amounts.'
                ) % delivery.name,
                subject=_('Delivery Finalized')
            )
            
            return True
            
        except Exception as e:
            _logger.warning(
                f"Subdeal {self.id}: Failed to finalize delivery {delivery.name} - {str(e)}"
            )
            self.deal_id.message_post(
                body=_('❌ Delivery validation failed: %s') % str(e)
            )
            return False
    
    def _finalize_receipt(self):
        """
        Update PO receipt with loaded quantities and validate.
        
        Flow:
        1. Find pending receipt (incoming picking not done/cancelled)
        2. Convert package quantities to units for stock moves
        3. Update move.quantity with converted units
        4. Validate picking (skip backorder dialog)
        5. Populate DM fields on stock moves for bill chain
        6. Update PO lines with qty_received_packages from deal
        7. Odoo auto-syncs PO.line.qty_received (in units)
        
        Returns:
            bool: True if successful, False otherwise
        """
        self.ensure_one()
        
        if not self.purchase_order_id:
            _logger.warning(f"Subdeal {self.id}: No PO linked for receipt finalization")
            return False
        
        # Chatter: Debug pickings
        picking_info = [(p.name, p.state, p.picking_type_id.code) for p in self.purchase_order_id.picking_ids]
        self.deal_id.message_post(
            body=_('🔍 PO Pickings found: %s') % str(picking_info)
        )
        
        # Find pending incoming picking
        receipt = self.purchase_order_id.picking_ids.filtered(
            lambda p: p.state not in ['done', 'cancel']
            and p.picking_type_id.code == 'incoming'
        )[:1]
        
        if not receipt:
            _logger.warning(
                f"Subdeal {self.id}: No pending receipt found for PO {self.purchase_order_id.name}. "
                f"Picking states: {self.purchase_order_id.picking_ids.mapped('state')}"
            )
            self.deal_id.message_post(
                body=_('⚠️ No pending incoming receipt found for PO %s') % self.purchase_order_id.name
            )
            return False
        
        # Chatter: Selected picking
        self.deal_id.message_post(
            body=_('🔍 Processing receipt: %s (state: %s)') % (receipt.name, receipt.state)
        )
        
        try:
            # Update quantities from subdeal lines
            moves_updated = 0
            move_details = []
            for move in receipt.move_ids:
                # Find matching subdeal line by product
                line = self.line_ids.filtered(
                    lambda l: l.product_id.id == move.product_id.id
                )[:1]
                
                if line:
                    if line.quantity_loaded and line.quantity_loaded > 0:
                        # Convert packages to units for stock system
                        units_qty = self._convert_packages_to_units(line)
                        move.quantity = units_qty
                        moves_updated += 1
                        move_details.append(
                            f"{move.product_id.name}: {line.quantity_loaded} pkg → {units_qty} units"
                        )
                        _logger.debug(
                            f"Receipt move {move.id}: Set quantity={units_qty} "
                            f"({line.quantity_loaded} packages) for {move.product_id.name}"
                        )
                    else:
                        move.quantity = 0
                        move_details.append(f"{move.product_id.name}: 0 (not loaded)")
                else:
                    _logger.warning(
                        f"Receipt move {move.id}: No matching subdeal line for {move.product_id.name}"
                    )
                    move.quantity = 0
                    move_details.append(f"{move.product_id.name}: 0 (no matching line)")
            
            # Chatter: Move updates
            self.deal_id.message_post(
                body=_('📦 Receipt moves updated:<br/>%s') % '<br/>'.join(move_details)
            )
            
            # Validate picking
            receipt.with_context(
                skip_backorder=True,
                cancel_backorder=True,
                skip_immediate=True
            ).button_validate()
            
            # Populate DM fields on validated moves for bill chain
            self._populate_stock_move_dm_fields(receipt)
            
            # Update PO lines with received packages from deal
            self._update_po_line_received_packages()
            
            _logger.info(
                f"Subdeal {self.id}: Finalized receipt {receipt.name} "
                f"({moves_updated} moves updated, state={receipt.state})"
            )
            
            # Chatter: Validation result
            self.deal_id.message_post(
                body=_('✅ Receipt %s validated (state: %s)') % (receipt.name, receipt.state)
            )
            
            # Post message to PO
            self.purchase_order_id.message_post(
                body=_(
                    'Receipt <b>%s</b> finalized from shipment loading.<br/>'
                    'Quantities updated from actual loaded amounts.'
                ) % receipt.name,
                subject=_('Receipt Finalized')
            )
            
            return True
            
        except Exception as e:
            _logger.warning(
                f"Subdeal {self.id}: Failed to finalize receipt {receipt.name} - {str(e)}"
            )
            self.deal_id.message_post(
                body=_('❌ Receipt validation failed: %s') % str(e)
            )
            return False