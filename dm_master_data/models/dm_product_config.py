from odoo import models, fields


class DmCollection(models.Model):
    _name = 'dm.collection'
    _description = 'Product Collection'
    _order = 'name'
    
    name = fields.Char(
        string='Collection Name',
        required=True,
        help='Name of the product collection'
    )
    description = fields.Text(
        string='Description',
        help='Description of the collection'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this collection will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Collection name must be unique!')
    ]


class DmPackageType(models.Model):
    _name = 'dm.package.type'
    _description = 'Package Type'
    _order = 'name'
    
    name = fields.Char(
        string='Package Type',
        required=True,
        help='Type of package (Bag, Box, etc.)'
    )
    description = fields.Text(
        string='Description',
        help='Description of the package type'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this package type will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Package type name must be unique!')
    ]


class DmIndividualPackingType(models.Model):
    _name = 'dm.individual.packing.type'
    _description = 'Individual Packing Type'
    _order = 'name'
    
    name = fields.Char(
        string='Individual Packing Type',
        required=True,
        help='Type of individual packing'
    )
    description = fields.Text(
        string='Description',
        help='Description of the individual packing type'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this packing type will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Individual packing type name must be unique!')
    ]


class DmTexture(models.Model):
    _name = 'dm.texture'
    _description = 'Product Texture'
    _order = 'name'
    
    name = fields.Char(
        string='Texture',
        required=True,
        help='Product texture'
    )
    description = fields.Text(
        string='Description',
        help='Description of the texture'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this texture will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Texture name must be unique!')
    ]


class DmStabilizer(models.Model):
    _name = 'dm.stabilizer'
    _description = 'Product Stabilizer'
    _order = 'name'
    
    name = fields.Char(
        string='Stabilizer',
        required=True,
        help='Product stabilizer (pectine, gelatine, etc.)'
    )
    description = fields.Text(
        string='Description',
        help='Description of the stabilizer'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this stabilizer will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Stabilizer name must be unique!')
    ]


class DmTasteFlavor(models.Model):
    _name = 'dm.taste.flavor'
    _description = 'Product Taste/Flavor'
    _order = 'name'
    
    name = fields.Char(
        string='Taste/Flavor',
        required=True,
        help='Product taste or flavor'
    )
    description = fields.Text(
        string='Description',
        help='Description of the taste/flavor'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this taste/flavor will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Taste/Flavor name must be unique!')
    ]


class DmShape(models.Model):
    _name = 'dm.shape'
    _description = 'Product Shape'
    _order = 'name'
    
    name = fields.Char(
        string='Shape',
        required=True,
        help='Product shape'
    )
    description = fields.Text(
        string='Description',
        help='Description of the shape'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this shape will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Shape name must be unique!')
    ]


class DmColor(models.Model):
    _name = 'dm.color'
    _description = 'Product Color'
    _order = 'name'
    
    name = fields.Char(
        string='Color',
        required=True,
        help='Product color'
    )
    hex_code = fields.Char(
        string='Hex Code',
        help='Hexadecimal color code (e.g., #FF0000 for red)'
    )
    description = fields.Text(
        string='Description',
        help='Description of the color'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this color will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Color name must be unique!')
    ]


class DmComplianceRegion(models.Model):
    _name = 'dm.compliance.region'
    _description = 'Compliance Region/Standard'
    _order = 'name'
    
    name = fields.Char(
        string='Region/Standard',
        required=True,
        help='Compliance region or standard (US, EU, etc.)'
    )
    description = fields.Text(
        string='Description',
        help='Description of the compliance requirements'
    )
    active = fields.Boolean(
        string='Active',
        default=True,
        help='If unchecked, this compliance region will be hidden from selection'
    )
    
    _sql_constraints = [
        ('name_uniq', 'unique (name)', 'Compliance region name must be unique!')
    ]