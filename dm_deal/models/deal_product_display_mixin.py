# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class DealProductDisplayMixin(models.AbstractModel):
    _name = 'deal.product.display.mixin'
    _description = 'Deal Product Display & Context Mixin'

    # Display-optimized fields
    display_product_name = fields.Char(
        string='Product',
        compute='_compute_display_fields',
        store=True,
        index=True
    )
    
    display_package_info = fields.Char(
        string='Package',
        compute='_compute_display_fields',
        store=True
    )
    
    display_category = fields.Char(
        string='Category',
        compute='_compute_display_fields',
        store=True,
        index=True
    )
    
    display_sort_key = fields.Integer(
        string='Sort Order',
        compute='_compute_display_fields',
        store=True,
        index=True
    )
    
    display_customer_po = fields.Char(
        string='Customer PO #',
        compute='_compute_display_customer_po',
        store=True,
        index=True
    )
    
    # Context fields for business logic
    is_master_package = fields.Boolean(
        string='Is Master Package',
        compute='_compute_context_fields',
        store=True
    )
    
    is_inner_package = fields.Boolean(
        string='Is Inner Package',
        compute='_compute_context_fields',
        store=True
    )
    
    requires_inner_specification = fields.Boolean(
        string='Requires Inner Specification',
        compute='_compute_context_fields',
        store=True
    )
    
    category_sequence = fields.Integer(
        string='Category Sequence',
        compute='_compute_context_fields',
        store=True
    )

    @api.depends('product_id', 'product_id.name', 'product_id.default_code')
    def _compute_display_fields(self):
        """Compute display-optimized fields for tree views."""
        for line in self:
            if not line.product_id:
                line.display_product_name = ''
                line.display_package_info = ''
                line.display_category = ''
                line.display_sort_key = 9999
                continue
            
            product = line.product_id
            
            # Product name with code
            if product.default_code:
                line.display_product_name = f"[{product.default_code}] {product.name}"
            else:
                line.display_product_name = product.name
            
            # Package info
            line.display_package_info = line._format_package_info()
            
            # Category
            line.display_category = line._get_display_category()
            
            # Sort key
            line.display_sort_key = line._get_sort_key()

    @api.depends('deal_id', 'deal_id.customer_po_number')
    def _compute_display_customer_po(self):
        """Compute customer PO number from parent deal."""
        for line in self:
            if hasattr(line, 'deal_id') and line.deal_id:
                line.display_customer_po = line.deal_id.customer_po_number or ''
            else:
                line.display_customer_po = ''

    @api.depends(
        'product_id',
        'product_id.master_package_id',
        'product_id.inner_package_id',
        'product_id.categ_id',
        'product_id.categ_id.display_sequence'
    )
    def _compute_context_fields(self):
        """Compute context fields for business logic."""
        for line in self:
            if not line.product_id:
                line.is_master_package = False
                line.is_inner_package = False
                line.requires_inner_specification = False
                line.category_sequence = 9999
                continue
            
            product = line.product_id
            
            # Package type flags
            line.is_master_package = bool(product.master_package_id)
            line.is_inner_package = bool(product.inner_package_id)
            
            # Inner specification requirement
            line.requires_inner_specification = (
                line.is_master_package and 
                not line.is_inner_package
            )
            
            # Category sequence
            if product.categ_id and hasattr(product.categ_id, 'display_sequence'):
                line.category_sequence = product.categ_id.display_sequence
            else:
                line.category_sequence = 9999

    def _format_package_info(self):
        """Format package information for display."""
        self.ensure_one()
        
        if not self.product_id:
            return ''
        
        product = self.product_id
        parts = []
        
        # Master package
        if product.master_package_id:
            master = product.master_package_id
            if master.units_per_package:
                parts.append(f"{int(master.units_per_package)} units")
        
        # Inner package
        if product.inner_package_id:
            inner = product.inner_package_id
            if inner.units_per_package:
                parts.append(f"({int(inner.units_per_package)} units/inner)")
        
        return ' • '.join(parts) if parts else ''

    def _get_display_category(self):
        """Get category name for display."""
        self.ensure_one()
        
        if not self.product_id or not self.product_id.categ_id:
            return 'Uncategorized'
        
        return self.product_id.categ_id.name

    def _get_sort_key(self):
        """Calculate sort key for tree ordering."""
        self.ensure_one()
        
        if not self.product_id:
            return 9999
        
        product = self.product_id
        category_seq = 9999
        
        if product.categ_id and hasattr(product.categ_id, 'display_sequence'):
            category_seq = product.categ_id.display_sequence or 9999
        
        # Sort: category first, then product name
        return category_seq * 10000 + (hash(product.name) % 10000)

    @api.model
    def _get_category_groups(self, lines):
        """
        Group lines by category for structured display.
        Returns: [(category_name, category_sequence, [lines]), ...]
        """
        from collections import defaultdict
        
        groups = defaultdict(list)
        
        for line in lines:
            category = line.display_category or 'Uncategorized'
            sequence = line.category_sequence if hasattr(line, 'category_sequence') else 9999
            groups[(category, sequence)].append(line)
        
        # Sort by sequence, then category name
        sorted_groups = sorted(groups.items(), key=lambda x: (x[0][1], x[0][0]))
        
        return [(cat_name, cat_seq, sorted(lines, key=lambda l: l.display_product_name))
                for (cat_name, cat_seq), lines in sorted_groups]

    @api.model
    def get_display_tree_fields(self, base_fields=None, extra_fields=None):
        """
        Get list of field definitions for tree views.
        
        Args:
            base_fields: list of tuples (field_name, attrs_dict)
            extra_fields: list of field names to append
            
        Returns:
            list of tuples (field_name, attrs_dict)
        """
        if base_fields is None:
            base_fields = [
                ('display_customer_po', {'string': 'Customer PO #', 'optional': 'show'}),
                ('display_product_name', {'string': 'Product'}),
                ('display_package_info', {'string': 'Package'}),
                ('display_category', {'string': 'Category', 'optional': 'hide'}),
            ]
        
        result = list(base_fields)
        
        if extra_fields:
            for field_name in extra_fields:
                result.append((field_name, {}))
        
        # Hidden context fields
        hidden_fields = [
            'display_sort_key',
            'is_master_package',
            'is_inner_package',
            'category_sequence',
        ]
        
        for field_name in hidden_fields:
            result.append((field_name, {'invisible': '1'}))
        
        return result

    @api.model
    def get_display_search_filters(self, extra_filters=None):
        """
        Get list of search filter definitions.
        
        Args:
            extra_filters: list of filter definition dicts
            
        Returns:
            list of filter definition dicts
        """
        base_filters = [
            {
                'type': 'field',
                'name': 'display_product_name',
                'string': 'Product',
                'filter_domain': "[('display_product_name', 'ilike', self)]"
            },
            {
                'type': 'field',
                'name': 'display_customer_po',
                'string': 'Customer PO #',
                'filter_domain': "[('display_customer_po', 'ilike', self)]"
            },
            {
                'type': 'field',
                'name': 'display_category',
                'string': 'Category'
            },
            {'type': 'separator'},
            {
                'type': 'filter',
                'name': 'filter_master',
                'string': 'Master Packages',
                'domain': "[('is_master_package', '=', True)]"
            },
            {
                'type': 'filter',
                'name': 'filter_inner',
                'string': 'Inner Packages',
                'domain': "[('is_inner_package', '=', True)]"
            },
            {
                'type': 'filter',
                'name': 'filter_needs_inner',
                'string': 'Requires Inner Spec',
                'domain': "[('requires_inner_specification', '=', True)]"
            },
        ]
        
        if extra_filters:
            base_filters.extend(extra_filters)
        
        return base_filters

    @api.model
    def get_display_search_groups(self, extra_groups=None):
        """
        Get list of search group_by definitions.
        
        Args:
            extra_groups: list of group_by definition dicts
            
        Returns:
            list of group_by definition dicts
        """
        base_groups = [
            {
                'name': 'group_category',
                'string': 'Category',
                'context': "{'group_by': 'display_category'}"
            },
            {
                'name': 'group_package_type',
                'string': 'Package Type',
                'context': "{'group_by': 'is_master_package'}"
            },
        ]
        
        if extra_groups:
            base_groups.extend(extra_groups)
        
        return base_groups