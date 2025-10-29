from odoo import fields, models, api
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class PackagingStandardType(models.Model):
    _name = 'packaging.standard.type'
    _description = 'Standard Packaging Type'
    _order = 'sequence, name'
    _rec_name = 'name'
    
    # ==========================================
    # CORE FIELDS
    # ==========================================
    
    name = fields.Char(
        string='Standard Type',
        required=True,
        help='Standard packaging type name (e.g., Carton, Pallet)'
    )
    
    code = fields.Char(
        string='Code',
        required=True,
        help='Uppercase code for integration (e.g., CARTON, PALLET)'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Display order in lists'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True,
        help='Deactivate to hide without deleting'
    )
    
    description = fields.Text(
        string='Description',
        help='Detailed description of this packaging type'
    )
    
    # ==========================================
    # CATEGORY FIELDS
    # ==========================================
    
    category = fields.Selection([
        ('unit', 'Unit Level'),
        ('inner', 'Inner Pack'),
        ('case', 'Case/Carton'),
        ('pallet', 'Pallet'),
        ('container', 'Container'),
        ('other', 'Other')
    ], string='Category', default='other',
       help='Hierarchical level of this packaging type')
    
    is_shipping_container = fields.Boolean(
        string='Is Shipping Container',
        default=False,
        help='Check if this represents a shipping container'
    )
    
    # ==========================================
    # RELATIONAL FIELDS
    # ==========================================
    
    packaging_ids = fields.One2many(
        'product.packaging',
        'standard_type_id',
        string='Packaging Using This Type'
    )
    
    packaging_count = fields.Integer(
        string='Packaging Count',
        compute='_compute_packaging_count',
        store=True
    )
    
    # ==========================================
    # COMPUTED METHODS
    # ==========================================
    
    @api.depends('packaging_ids')
    def _compute_packaging_count(self):
        """Count number of packaging records using this standard type"""
        for record in self:
            record.packaging_count = len(record.packaging_ids)
    
    # ==========================================
    # CONSTRAINT METHODS
    # ==========================================
    
    @api.constrains('code')
    def _check_code_unique(self):
        """Ensure code is unique among active records"""
        for record in self:
            if record.code:
                duplicate = self.search([
                    ('code', '=', record.code),
                    ('active', '=', True),
                    ('id', '!=', record.id)
                ], limit=1)
                if duplicate:
                    raise ValidationError(
                        f"Code '{record.code}' is already used by '{duplicate.name}'. "
                        f"Codes must be unique among active standard types."
                    )
    
    @api.constrains('code')
    def _check_code_uppercase(self):
        """Ensure code is uppercase for consistency"""
        for record in self:
            if record.code and record.code != record.code.upper():
                raise ValidationError(
                    f"Code must be uppercase. Use '{record.code.upper()}' instead of '{record.code}'."
                )
    
    # ==========================================
    # CRUD METHODS
    # ==========================================
    
    @api.model_create_multi
    def create(self, vals_list):
        """Auto-uppercase code on creation"""
        for vals in vals_list:
            if 'code' in vals and vals['code']:
                vals['code'] = vals['code'].upper()
        return super().create(vals_list)
    
    def write(self, vals):
        """Auto-uppercase code on update"""
        if 'code' in vals and vals['code']:
            vals['code'] = vals['code'].upper()
        return super().write(vals)
    
    # ==========================================
    # BUSINESS METHODS
    # ==========================================
    
    def get_packaging_by_standard_type(self, product_id=None):
        """Get all packaging records using this standard type
        
        Args:
            product_id: Optional product to filter by
            
        Returns:
            product.packaging recordset
        """
        self.ensure_one()
        domain = [('standard_type_id', '=', self.id)]
        if product_id:
            domain.append(('product_id', '=', product_id))
        return self.env['product.packaging'].search(domain)
    
    @api.model
    def get_carton_type(self):
        """Quick helper to get the CARTON standard type"""
        return self.search([('code', '=', 'CARTON'), ('active', '=', True)], limit=1)
    
    @api.model
    def get_pallet_type(self):
        """Quick helper to get the PALLET standard type"""
        return self.search([('code', '=', 'PALLET'), ('active', '=', True)], limit=1)
    
    @api.model
    def get_container_type(self):
        """Quick helper to get the CONTAINER standard type"""
        return self.search([('code', '=', 'CONTAINER'), ('active', '=', True)], limit=1)
    
    # ==========================================
    # DISPLAY METHODS
    # ==========================================
    
    def name_get(self):
        """Display name with code"""
        result = []
        for record in self:
            if record.code:
                name = f"{record.name} [{record.code}]"
            else:
                name = record.name
            result.append((record.id, name))
        return result
    
    @api.model
    def _name_search(self, name, args=None, operator='ilike', limit=100, order=None):
        """Search by name or code"""
        args = args or []
        if name:
            args = ['|', ('name', operator, name), ('code', operator, name)] + args
        return self._search(args, limit=limit, order=order)