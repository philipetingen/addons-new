from odoo import models, fields, api


class DmQcType(models.Model):
    """
    QC checklist types for production.
    Simplified to pass/fail checks without blocking.
    """
    _name = 'dm.qc_type'
    _description = 'QC Check Type'
    _order = 'sequence, name'
    _rec_name = 'name'
    
    name = fields.Char(
        string='QC Check',
        required=True,
        help='Name of the QC check'
    )
    
    code = fields.Char(
        string='Code',
        size=10,
        help='Short code for the check'
    )
    
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help='Order of checks'
    )
    
    category = fields.Selection([
        ('visual', 'Visual Inspection'),
        ('dimensional', 'Dimensional Check'),
        ('weight', 'Weight Verification'),
        ('packaging', 'Packaging Check'),
        ('labeling', 'Labeling Check'),
        ('documentation', 'Documentation'),
        ('temperature', 'Temperature Check'),
        ('moisture', 'Moisture Check'),
        ('chemical', 'Chemical Analysis'),
        ('microbiological', 'Microbiological'),
        ('other', 'Other')
    ], string='Category', default='visual', required=True)
    
    check_point = fields.Selection([
        ('raw_material', 'Raw Material'),
        ('in_process', 'In Process'),
        ('finished', 'Finished Product'),
        ('pre_loading', 'Pre-Loading'),
        ('post_loading', 'Post-Loading')
    ], string='Check Point', default='finished', required=True)
    
    # Check details
    check_method = fields.Text(
        string='Check Method',
        help='How to perform this check'
    )
    
    acceptance_criteria = fields.Text(
        string='Acceptance Criteria',
        help='Criteria for passing this check'
    )
    
    # Sampling
    requires_sampling = fields.Boolean(
        string='Requires Sampling',
        default=False
    )
    
    sample_size = fields.Char(
        string='Sample Size',
        help='Required sample size or percentage'
    )
    
    sample_method = fields.Text(
        string='Sampling Method',
        help='How to collect samples'
    )
    
    # Documentation
    requires_photo = fields.Boolean(
        string='Requires Photo',
        default=False,
        help='Photo evidence required'
    )
    
    requires_certificate = fields.Boolean(
        string='Requires Certificate',
        default=False,
        help='Certificate required for this check'
    )
    
    # Control
    is_critical = fields.Boolean(
        string='Critical Check',
        default=False,
        help='Critical quality check (for reporting only)'
    )
    
    active = fields.Boolean(
        string='Active',
        default=True
    )
    
    @api.model
    def get_required_checks(self, product_id=None, check_point='finished'):
        """
        Get required QC checks for a product at a check point.
        
        Args:
            product_id: Product to check
            check_point: Point in process
            
        Returns:
            recordset: Required QC types
        """
        domain = [
            ('active', '=', True),
            ('check_point', '=', check_point)
        ]
        
        checks = self.search(domain, order='sequence, name')
        
        # Add product-specific checks
        if product_id:
            product = self.env['product.product'].browse(product_id)
            if product.required_qc_type_ids:
                checks |= product.required_qc_type_ids
        
        return checks