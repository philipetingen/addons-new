from odoo import models, fields, api


class DmDocumentType(models.Model):
    """
    Document type definitions for compliance tracking.
    Simplified to source/route tracking with checklists.
    """
    _name = 'dm.document.type'
    _description = 'Document Type'
    _order = 'sequence, name'
    _rec_name = 'name'
    
    name = fields.Char(
        string='Document Type',
        required=True,
        help='Name of the document type'
    )
    
    code = fields.Char(
        string='Code',
        size=10,
        help='Short code for the document'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display sequence'
    )
    
    category = fields.Selection([
        ('commercial', 'Commercial'),
        ('transport', 'Transport'),
        ('customs', 'Customs'),
        ('quality', 'Quality'),
        ('regulatory', 'Regulatory'),
        ('financial', 'Financial'),
        ('other', 'Other')
    ], string='Category', default='commercial', required=True)
    
    document_source = fields.Selection([
        ('customer', 'From Customer'),
        ('supplier', 'From Supplier'),
        ('internal', 'Internal'),
        ('government', 'Government'),
        ('third_party', 'Third Party')
    ], string='Document Source', required=True, default='internal')
    
    # When is it required
    required_for = fields.Selection([
        ('always', 'Always Required'),
        ('export', 'Export Only'),
        ('import', 'Import Only'),
        ('dangerous', 'Dangerous Goods Only'),
        ('reefer', 'Refrigerated Only'),
        ('conditional', 'Conditional')
    ], string='Required For', default='always')
    
    # Timing
    required_before = fields.Selection([
        ('booking', 'Before Booking'),
        ('production', 'Before Production'),
        ('loading', 'Before Loading'),
        ('departure', 'Before Departure'),
        ('arrival', 'Before Arrival'),
        ('delivery', 'Before Delivery')
    ], string='Required Before', default='loading')
    
    # Validity
    has_expiry = fields.Boolean(
        string='Has Expiry',
        default=False,
        help='Document has an expiration date'
    )
    
    validity_days = fields.Integer(
        string='Validity (Days)',
        help='Number of days the document is valid'
    )
    
    # Checklist items
    checklist_items = fields.Text(
        string='Checklist Items',
        help='Checklist items for this document (one per line)'
    )
    
    # Instructions
    instructions = fields.Text(
        string='Instructions',
        help='Instructions for obtaining/completing this document'
    )
    
    # Control
    is_mandatory = fields.Boolean(
        string='Mandatory',
        default=True,
        help='Document is mandatory when applicable'
    )
    
    blocks_shipment = fields.Boolean(
        string='Blocks Shipment',
        default=False,
        help='Missing document blocks shipment (future implementation)'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    @api.model
    def get_required_documents(self, product_id=None, route=None, shipment_type=None):
        """
        Get list of required documents based on context.
        
        Args:
            product_id: Product being shipped
            route: Shipping route (export/import)
            shipment_type: Type of shipment
            
        Returns:
            recordset: Required document types
        """
        domain = [('active', '=', True)]
        
        # Filter by requirement conditions
        conditions = ['always']
        
        if route == 'export':
            conditions.append('export')
        elif route == 'import':
            conditions.append('import')
        
        if product_id:
            product = self.env['product.product'].browse(product_id)
            if product.is_dangerous_goods:
                conditions.append('dangerous')
            if product.requires_refrigeration:
                conditions.append('reefer')
        
        domain.append(('required_for', 'in', conditions))
        
        return self.search(domain, order='sequence, name')
    
    def get_checklist(self):
        """
        Get checklist items as a list.
        
        Returns:
            list: Checklist items
        """
        self.ensure_one()
        
        if not self.checklist_items:
            return []
        
        return [item.strip() for item in self.checklist_items.split('\n') if item.strip()]