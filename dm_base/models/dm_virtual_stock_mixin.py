from odoo import models, fields, api
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmVirtualStockMixin(models.AbstractModel):
    """
    Virtual stock management mixin for shipment transit operations.
    
    Per Appendix Section 6: Virtual Stock Operations
    Creates paired receipt/delivery movements that net to zero.
    """
    _name = 'dm.virtual.stock.mixin'
    _description = 'DonnaMello Virtual Stock Mixin'
    
    # Virtual stock movements
    virtual_receipt_id = fields.Many2one(
        'stock.picking',
        string='Virtual Receipt',
        readonly=True,
        help='Virtual receipt into transit location'
    )
    
    virtual_delivery_id = fields.Many2one(
        'stock.picking',
        string='Virtual Delivery',
        readonly=True,
        help='Virtual delivery from transit location'
    )
    
    virtual_location_id = fields.Many2one(
        'stock.location',
        string='Virtual Location',
        compute='_compute_virtual_location',
        help='Virtual transit location for this operation'
    )
    
    @api.depends()
    def _compute_virtual_location(self):
        """Get or create virtual transit location."""
        for record in self:
            record.virtual_location_id = record._get_virtual_location()
    
    def _get_virtual_location(self):
        """
        Get the virtual transit location for DM operations.
        Creates if not exists.
        """
        # Try to get from system parameters
        param = self.env['ir.config_parameter'].sudo()
        location_id = param.get_param('dm.virtual_location_id')
        
        if location_id:
            location = self.env['stock.location'].browse(int(location_id))
            if location.exists():
                return location
        
        # Create if not exists
        location = self.env['stock.location'].sudo().create({
            'name': 'DM Virtual Transit',
            'usage': 'internal',
            'comment': 'Virtual location for DonnaMello transit operations',
            'active': True
        })
        
        # Save to parameters
        param.set_param('dm.virtual_location_id', location.id)
        
        _logger.info(f"Created virtual transit location: {location.name}")
        
        return location
    
    def create_virtual_movements(self, lines, reference=None):
        """
        Create paired virtual stock movements that net to zero.
        
        Args:
            lines: List of dicts with product/quantity info
            reference: Reference for the movements
            
        Returns:
            tuple: (receipt_picking, delivery_picking)
        """
        if not lines:
            raise UserError("Cannot create virtual movements without lines")
        
        Picking = self.env['stock.picking']
        Move = self.env['stock.move']
        
        virtual_location = self._get_virtual_location()
        warehouse = self.env['stock.warehouse'].search([], limit=1)
        
        if not warehouse:
            raise UserError("No warehouse configured")
        
        # Create virtual receipt (IN)
        receipt_vals = {
            'picking_type_id': warehouse.in_type_id.id,
            'location_id': self.env.ref('stock.stock_location_suppliers').id,
            'location_dest_id': virtual_location.id,
            'origin': reference or f"Virtual IN - {self.display_name}",
            'scheduled_date': fields.Datetime.now(),
        }
        
        virtual_receipt = Picking.create(receipt_vals)
        
        # Create virtual delivery (OUT)
        delivery_vals = {
            'picking_type_id': warehouse.out_type_id.id,
            'location_id': virtual_location.id,
            'location_dest_id': self.env.ref('stock.stock_location_customers').id,
            'origin': reference or f"Virtual OUT - {self.display_name}",
            'scheduled_date': fields.Datetime.now(),
        }
        
        virtual_delivery = Picking.create(delivery_vals)
        
        # Create moves for each line
        for line in lines:
            product = line.get('product_id')
            quantity = line.get('quantity', 0)
            packaging = line.get('packaging_id')
            
            if not product or quantity <= 0:
                continue
            
            # Common move values
            move_base = {
                'name': product.display_name,
                'product_id': product.id,
                'product_uom_qty': quantity,
                'product_uom': product.uom_id.id,
                'product_packaging_id': packaging.id if packaging else False,
            }
            
            # Receipt move
            receipt_move_vals = {
                **move_base,
                'picking_id': virtual_receipt.id,
                'location_id': virtual_receipt.location_id.id,
                'location_dest_id': virtual_receipt.location_dest_id.id,
            }
            Move.create(receipt_move_vals)
            
            # Delivery move (same quantity)
            delivery_move_vals = {
                **move_base,
                'picking_id': virtual_delivery.id,
                'location_id': virtual_delivery.location_id.id,
                'location_dest_id': virtual_delivery.location_dest_id.id,
            }
            Move.create(delivery_move_vals)
        
        # Auto-confirm and done both movements
        for picking in [virtual_receipt, virtual_delivery]:
            picking.action_confirm()
            picking.action_assign()
            
            # Force availability
            for move in picking.move_ids:
                move.quantity_done = move.product_uom_qty
            
            picking.button_validate()
        
        # Validate net zero
        self._validate_virtual_stock_zero(virtual_location, product_ids=[l['product_id'] for l in lines])
        
        # Store references
        self.write({
            'virtual_receipt_id': virtual_receipt.id,
            'virtual_delivery_id': virtual_delivery.id,
        })
        
        _logger.info(f"Created virtual movements: IN {virtual_receipt.name}, OUT {virtual_delivery.name}")
        
        return (virtual_receipt, virtual_delivery)
    
    def _validate_virtual_stock_zero(self, location, product_ids=None):
        """
        Validate that virtual location has zero net stock.
        
        Args:
            location: Virtual stock location
            product_ids: Optional list of products to check
            
        Raises:
            UserError: If stock is not zero
        """
        domain = [('location_id', '=', location.id)]
        
        if product_ids:
            domain.append(('product_id', 'in', [p.id for p in product_ids]))
        
        quants = self.env['stock.quant'].search(domain)
        
        for quant in quants:
            if abs(quant.quantity) > 0.001:  # Allow tiny rounding differences
                if hasattr(self, '_raise_user_error'):
                    self._raise_user_error('DM006',
                                         product=quant.product_id.display_name,
                                         quantity=quant.quantity)
                else:
                    raise UserError(
                        f"Virtual stock imbalance for {quant.product_id.display_name}: "
                        f"{quant.quantity:.3f} in {location.name}"
                    )
        
        _logger.info(f"Virtual stock validation passed for location {location.name}")
        
        return True
    
    def cancel_virtual_movements(self):
        """Cancel virtual stock movements if not done."""
        for picking in [self.virtual_receipt_id, self.virtual_delivery_id]:
            if picking and picking.state not in ['done', 'cancel']:
                picking.action_cancel()
                _logger.info(f"Cancelled virtual movement: {picking.name}")