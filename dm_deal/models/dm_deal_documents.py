from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class DmDealDocuments(models.Model):
    """Deal Documents Extension - SO/PO Creation"""
    _inherit = 'dm.deal'
    _description = 'Deal - Documents Extension'
    
    # ============================================================
    # SO/PO CREATION METHODS
    # ============================================================
    
    def _create_sale_order(self):
        """
        Create Sales Order with package-native quantities.
        
        CRITICAL MAPPINGS:
        - Currency: deal.currency_id
        - Quantities: package quantities (NOT units)
        - UoM: packaging_uom_id (package UoM)
        - Prices: 6-decimal package prices
        - Incoterm location: discharge_port_id.name
        - Commitment date: ETA (customer arrival expectation)
        """
        self.ensure_one()
        
        if not self.customer_id:
            raise UserError(_('Customer is required to create Sales Order'))
        
        if not self.line_ids:
            raise UserError(_('Cannot create SO without deal lines'))
        
        SaleOrder = self.env['sale.order']
        
        # Get pricelist matching deal currency
        pricelist = self._get_customer_pricelist()
        
        # Prepare SO values
        so_vals = {
            'partner_id': self.customer_id.id,
            'client_order_ref': self.customer_po_number,
            'date_order': fields.Datetime.now(),
            
            # Use deal currency explicitly
            'currency_id': self.currency_id.id,
            
            # Pricelist matching deal currency
            'pricelist_id': pricelist.id,
            
            # Payment terms
            'payment_term_id': self.sale_payment_term_id.id if self.sale_payment_term_id else False,
            
            # Incoterms with proper location
            'incoterm': self.sale_incoterm_id.id if self.sale_incoterm_id else False,
            'incoterm_location': self.discharge_port_id.name if self.discharge_port_id else self.sale_incoterm_location or '',
            
            # Commitment date = ETA
            'commitment_date': self.eta_current or self.eta_requested or False,
            
            # Deal reference
            'dm_deal_id': self.id,
            
            # Notes
            'note': (
                f"Deal: {self.name}\n"
                f"Customer PO: {self.customer_po_number}\n"
                f"Ports: {self.loading_port_id.name if self.loading_port_id else 'TBD'} → "
                f"{self.discharge_port_id.name if self.discharge_port_id else 'TBD'}"
            ),
            
            # Order lines
            'order_line': []
        }
        
        # Create SO lines from deal lines
        for line in self.line_ids:
            if not line.product_id or not line.product_packaging_id:
                _logger.warning(f"Skipping deal line without product/packaging: {line.id}")
                continue
            
            # Ensure packaging UoM exists
            if not line.packaging_uom_id:
                raise UserError(
                    f"Package UoM not found for product '{line.product_id.name}' "
                    f"with packaging '{line.product_packaging_id.name}'. "
                    f"Please check packaging configuration."
                )
            
            so_line_vals = {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                
                # CRITICAL: Use package quantities
                'product_uom_qty': line.quantity_packaging,
                'product_uom': line.packaging_uom_id.id,
                'product_packaging_id': line.product_packaging_id.id,
                
                # CRITICAL: Use package price with 6-decimal precision
                'price_unit': line.price_packaging_sale,
                
                'discount': 0.0,
                
                # Taxes from product
                'tax_id': [(6, 0, line.product_id.taxes_id.ids)],
                
                # Customer lead time
                'customer_lead': 0,
                
                # Link back to deal line
                'dm_deal_line_id': line.id,
            }
            
            so_vals['order_line'].append((0, 0, so_line_vals))
        
        # Validation
        if not so_vals['order_line']:
            raise UserError(_('No valid lines to create Sales Order'))
        
        # Create the SO
        try:
            so = SaleOrder.create(so_vals)
            
            # Link SO back to deal
            self.sale_order_ids = [(4, so.id)]
            
            # Link SO lines back to deal lines
            for so_line in so.order_line:
                if so_line.dm_deal_line_id:
                    so_line.dm_deal_line_id.sale_order_line_id = so_line.id
            
            _logger.info(
                f"✓ Created SO {so.name} for deal {self.name}:\n"
                f"  - Currency: {self.currency_id.name}\n"
                f"  - Lines: {len(so.order_line)}\n"
                f"  - Total: {so.amount_total:.2f} {so.currency_id.name}\n"
                f"  - Incoterm: {so.incoterm.code if so.incoterm else 'N/A'} {so.incoterm_location or ''}\n"
                f"  - ETA: {so.commitment_date or 'Not set'}"
            )
            
            return so
            
        except Exception as e:
            _logger.error(f"✗ Failed to create SO for deal {self.name}: {str(e)}")
            raise UserError(_(f"Failed to create Sales Order: {str(e)}"))

    def _get_customer_pricelist(self):
        """Get pricelist matching deal currency"""
        self.ensure_one()
        
        # Search for pricelist with naming convention
        pricelist_name = f"{self.customer_id.name} Pricelist ({self.currency_id.name})"
        
        pricelist = self.env['product.pricelist'].search([
            ('name', '=', pricelist_name),
            ('currency_id', '=', self.currency_id.id),
            ('company_id', 'in', [self.company_id.id, False]),
            ('active', '=', True)
        ], limit=1)
        
        if pricelist:
            _logger.info(
                f"✓ Found pricelist '{pricelist.name}' for {self.customer_id.name} "
                f"in {self.currency_id.name}"
            )
            return pricelist
        
        # Fallback: use customer's default
        pricelist = self.customer_id.property_product_pricelist
        
        if pricelist.currency_id != self.currency_id:
            _logger.warning(
                f"⚠ No pricelist found in {self.currency_id.name} for {self.customer_id.name}. "
                f"Using default pricelist ({pricelist.currency_id.name}). Currency mismatch!"
            )
        
        return pricelist
    
    def _create_purchase_order(self):
        """
        Create Purchase Order with package-native quantities.
        
        CRITICAL MAPPINGS:
        - Currency: deal.currency_id
        - Quantities: package quantities (NOT units)
        - UoM: packaging_uom_id (package UoM)
        - Prices: 6-decimal package prices
        - Incoterm location: loading_port_id.name
        - Expected date: production_start_calculated
        """
        self.ensure_one()
        
        if not self.supplier_id:
            _logger.info(f"No supplier set for deal {self.name}, skipping PO creation")
            return False
        
        if not self.line_ids:
            raise UserError(_('Cannot create PO without deal lines'))
        
        PurchaseOrder = self.env['purchase.order']
        
        # Prepare PO values
        po_vals = {
            'partner_id': self.supplier_id.id,
            'partner_ref': self.customer_po_number,  # Our PO# as their reference
            'date_order': fields.Datetime.now(),
            
            # Use deal currency explicitly
            'currency_id': self.currency_id.id,
            
            # Payment terms
            'payment_term_id': self.purchase_payment_term_id.id if self.purchase_payment_term_id else False,
            
            # Incoterms with proper location
            'incoterm_id': self.purchase_incoterm_id.id if self.purchase_incoterm_id else False,
            'incoterm_location': self.loading_port_id.name if self.loading_port_id else self.purchase_incoterm_location or '',
            
            # Expected date = production_start_calculated
            'date_planned': self.production_start_calculated or self.rts_current or self.rts_requested or fields.Date.today(),
            
            # Deal reference
            'dm_deal_id': self.id,
            
            # Notes
            'notes': (
                f"Deal: {self.name}\n"
                f"Customer PO: {self.customer_po_number}\n"
                f"Production Start: {self.production_start_calculated or 'TBD'}\n"
                f"RTS Target: {self.rts_current or self.rts_requested or 'TBD'}\n"
                f"Loading Port: {self.loading_port_id.name if self.loading_port_id else 'TBD'}"
            ),
            
            # Order lines
            'order_line': []
        }
        
        # Create PO lines from deal lines
        for line in self.line_ids:
            if not line.product_id or not line.product_packaging_id:
                _logger.warning(f"Skipping deal line without product/packaging: {line.id}")
                continue
            
            # Ensure packaging UoM exists
            if not line.packaging_uom_id:
                raise UserError(
                    f"Package UoM not found for product '{line.product_id.name}' "
                    f"with packaging '{line.product_packaging_id.name}'. "
                    f"Please check packaging configuration."
                )
            
            po_line_vals = {
                'product_id': line.product_id.id,
                'name': line.product_id.display_name,
                
                # CRITICAL: Use package quantities
                'product_qty': line.quantity_packaging,
                'product_uom': line.packaging_uom_id.id,
                'product_packaging_id': line.product_packaging_id.id,
                
                # CRITICAL: Use package price with 6-decimal precision
                'price_unit': line.price_packaging_purchase,
                
                # Delivery date
                'date_planned': po_vals['date_planned'],
                
                # Taxes from product
                'taxes_id': [(6, 0, line.product_id.supplier_taxes_id.ids)],
                
                # Link back to deal line
                'dm_deal_line_id': line.id,
            }
            
            po_vals['order_line'].append((0, 0, po_line_vals))
        
        # Validation
        if not po_vals['order_line']:
            raise UserError(_('No valid lines to create Purchase Order'))
        
        # Create the PO
        try:
            po = PurchaseOrder.create(po_vals)
            
            # Link PO back to deal
            self.purchase_order_ids = [(4, po.id)]
            
            # Link PO lines back to deal lines
            for po_line in po.order_line:
                if po_line.dm_deal_line_id:
                    po_line.dm_deal_line_id.purchase_order_line_id = po_line.id
            
            _logger.info(
                f"✓ Created PO {po.name} for deal {self.name}:\n"
                f"  - Currency: {self.currency_id.name}\n"
                f"  - Lines: {len(po.order_line)}\n"
                f"  - Total: {po.amount_total:.2f} {po.currency_id.name}\n"
                f"  - Incoterm: {po.incoterm_id.code if po.incoterm_id else 'N/A'} {po.incoterm_location or ''}\n"
                f"  - Expected: {po.date_planned}"
            )
            
            return po
            
        except Exception as e:
            _logger.error(f"✗ Failed to create PO for deal {self.name}: {str(e)}")
            raise UserError(_(f"Failed to create Purchase Order: {str(e)}"))