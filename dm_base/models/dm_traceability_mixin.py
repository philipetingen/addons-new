from odoo import models, fields, api
import logging

_logger = logging.getLogger(__name__)


class DmTraceabilityMixin(models.AbstractModel):
    """
    Traceability mixin for maintaining references across the document chain.
    
    Ensures critical references (deal_id, production_run_id, shipment_id) 
    are maintained throughout the system for complete traceability.
    """
    _name = 'dm.traceability.mixin'
    _description = 'DonnaMello Traceability Mixin'
    
    # Core traceability fields
    customer_po_number = fields.Char(
        string='Customer PO#',
        required=True,
        tracking=True,
        index=True,
        help='Customer Purchase Order Number - mandatory for all deals'
    )
    
    deal_id = fields.Many2one(
        'dm.deal',
        string='Source Deal',
        ondelete='restrict',
        index=True,
        help='Original deal this record traces back to'
    )
    
    production_run_id = fields.Many2one(
        'dm.production.run',
        string='Production Run',
        ondelete='restrict',
        index=True,
        help='Production run associated with this record'
    )
    
    shipment_id = fields.Many2one(
        'dm.shipment',
        string='Shipment',
        ondelete='restrict',
        index=True,
        help='Shipment associated with this record'
    )
    
    # Traceability chain
    traceability_chain = fields.Text(
        string='Traceability Chain',
        compute='_compute_traceability_chain',
        help='Complete traceability path for this record'
    )
    
    @api.depends('deal_id', 'production_run_id', 'shipment_id', 'customer_po_number')
    def _compute_traceability_chain(self):
        """Build the complete traceability chain."""
        for record in self:
            chain_parts = []
            
            # Customer PO is always first
            if record.customer_po_number:
                chain_parts.append(f"PO: {record.customer_po_number}")
            
            # Add deal reference
            if record.deal_id:
                chain_parts.append(f"Deal: {record.deal_id.name}")
            
            # Add production reference
            if record.production_run_id:
                chain_parts.append(f"PR: {record.production_run_id.name}")
            
            # Add shipment reference
            if record.shipment_id:
                chain_parts.append(f"Ship: {record.shipment_id.name}")
            
            record.traceability_chain = " → ".join(chain_parts) if chain_parts else "No traceability"
    
    def copy_traceability(self, source):
        """
        Copy traceability fields from source record.
        
        Args:
            source: Source record with traceability fields
        """
        traceability_fields = [
            'customer_po_number',
            'deal_id',
            'production_run_id',
            'shipment_id'
        ]
        
        values = {}
        for field in traceability_fields:
            if hasattr(source, field):
                values[field] = getattr(source, field)
        
        if values:
            self.write(values)
            _logger.info(f"Copied traceability from {source._name} to {self._name}")
    
    def validate_traceability(self):
        """
        Validate that required traceability fields are present.
        Customer PO# is always required.
        """
        for record in self:
            if not record.customer_po_number:
                if hasattr(record, '_raise_user_error'):
                    record._raise_user_error('DM020')
                else:
                    raise UserError("Customer PO Number is required")
        
        return True
    
    def get_traceability_documents(self):
        """
        Get all related documents in the traceability chain.
        
        Returns:
            dict: Related documents by type
        """
        self.ensure_one()
        
        documents = {
            'deals': self.env['dm.deal'],
            'production_runs': self.env['dm.production.run'],
            'shipments': self.env['dm.shipment'],
            'sale_orders': self.env['sale.order'],
            'purchase_orders': self.env['purchase.order'],
            'invoices': self.env['account.move'],
        }
        
        # Find deal
        if self.deal_id:
            documents['deals'] |= self.deal_id
            
            # Find related SOs/POs
            if self.deal_id.sale_order_ids:
                documents['sale_orders'] |= self.deal_id.sale_order_ids
            if self.deal_id.purchase_order_ids:
                documents['purchase_orders'] |= self.deal_id.purchase_order_ids
        
        # Find production run
        if self.production_run_id:
            documents['production_runs'] |= self.production_run_id
        
        # Find shipment
        if self.shipment_id:
            documents['shipments'] |= self.shipment_id
        
        # Find by Customer PO#
        if self.customer_po_number:
            # Search all related models
            documents['deals'] |= self.env['dm.deal'].search([
                ('customer_po_number', '=', self.customer_po_number)
            ])
            documents['sale_orders'] |= self.env['sale.order'].search([
                ('client_order_ref', '=', self.customer_po_number)
            ])
        
        return documents