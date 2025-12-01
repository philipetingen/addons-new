# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class DmDealSubdealWorkflow(models.Model):
    """
    Sub-Deal Workflow Extension
    
    Additional workflow methods and validations for sub-deals.
    Core workflow is in dm_deal_subdeal.py - this adds extras.
    """
    _inherit = 'dm.deal.subdeal'
    
    # =========================================================================
    # WORKFLOW VALIDATIONS
    # =========================================================================
    
    def _validate_can_confirm(self):
        """Validate subdeal can be confirmed"""
        self.ensure_one()
        
        errors = []
        
        if not self.line_ids:
            errors.append('No lines in subdeal')
        
        if not self.deal_id.customer_id:
            errors.append('No customer set')
        
        for line in self.line_ids:
            if line.quantity_packaging <= 0:
                errors.append(f'Line {line.sequence}: Invalid quantity')
        
        if errors:
            raise UserError(_('Cannot confirm subdeal:\n%s') % '\n'.join(errors))
    
    def _validate_can_start_production(self):
        """Validate production can start"""
        self.ensure_one()
        
        # FIXED: 'validated' doesn't exist on subdeal
        if self.state not in ['draft', 'confirmed']:
            raise UserError(_(
                'Can only start production from draft or confirmed state.\n'
                'Current state: %s'
            ) % self.state)
    
    def _validate_can_mark_ready(self):
        """Validate can mark ready"""
        self.ensure_one()
        
        if self.state != 'in_production':
            raise UserError(_(
                'Can only mark ready from in_production state.\n'
                'Current state: %s'
            ) % self.state)
    
    # =========================================================================
    # ENHANCED WORKFLOW METHODS
    # =========================================================================
    
    def action_confirm(self):
        """Enhanced confirmation with validation"""
        for subdeal in self:
            subdeal._validate_can_confirm()
        
        return super().action_confirm()
    
    def action_start_production(self):
        """Enhanced production start with validation"""
        for subdeal in self:
            subdeal._validate_can_start_production()
        
        return super().action_start_production()
    
    def action_mark_ready(self):
        """Enhanced ready marking with validation"""
        for subdeal in self:
            subdeal._validate_can_mark_ready()
        
        return super().action_mark_ready()