import logging
from odoo import models, fields, api
from datetime import timedelta

_logger = logging.getLogger(__name__)


class DmCascadeMixin(models.AbstractModel):
    """
    CASCADE engine mixin implementing the three-layer date CASCADE system.
    
    Provides generic CASCADE functionality with:
    - Loop prevention
    - Comprehensive logging
    - Date, quantity, and state cascading
    
    As per Appendix Section 5: CASCADE Operations
    """
    _name = 'dm.cascade.mixin'
    _description = 'DonnaMello CASCADE Engine Mixin'
    
    cascade_in_progress = fields.Boolean(
        string='CASCADE In Progress',
        default=False,
        help='Flag to prevent CASCADE loops'
    )
    
    cascade_log = fields.Text(
        string='CASCADE Log',
        help='Log of CASCADE operations for audit'
    )
    
    # Three-layer date fields (common across modules)
    requested_date = fields.Date(
        string='Requested Date',
        help='Customer/Business requested date'
    )
    
    planned_date = fields.Date(
        string='Planned Date',
        help='Internally planned date'
    )
    
    actual_date = fields.Date(
        string='Actual Date',
        help='Actual execution date'
    )
    
    def _cascade_changes(self, trigger_field, old_value, new_value, context=None):
        """
        Generic CASCADE handler with loop prevention and logging.
        
        Args:
            trigger_field: Field that triggered the CASCADE
            old_value: Previous value
            new_value: New value
            context: Additional context for CASCADE rules
        
        Returns:
            dict: Results of CASCADE operations
        """
        if self.cascade_in_progress:
            _logger.info(f"CASCADE loop prevented for {trigger_field}")
            return {'status': 'loop_prevented'}
        
        self.cascade_in_progress = True
        results = {'status': 'success', 'cascaded_to': []}
        
        try:
            # Log CASCADE operation
            log_entry = (
                f"\n[{fields.Datetime.now()}] CASCADE TRIGGERED\n"
                f"Field: {trigger_field}\n"
                f"Old Value: {old_value}\n"
                f"New Value: {new_value}\n"
                f"Record: {self.display_name} (ID: {self.id})\n"
            )
            
            # Get CASCADE rules for this model and field
            rules = self._get_cascade_rules()
            applicable_rules = rules.get(trigger_field, [])
            
            for rule in applicable_rules:
                try:
                    result = self._apply_cascade_rule(rule, old_value, new_value, context)
                    if result:
                        results['cascaded_to'].append(result)
                        log_entry += f"Applied rule: {rule.get('name', 'Unnamed')}\n"
                except Exception as e:
                    _logger.error(f"CASCADE rule failed: {e}")
                    log_entry += f"Rule failed: {str(e)}\n"
            
            # Update log
            existing_log = self.cascade_log or ""
            self.cascade_log = existing_log + log_entry
            
            # Notify if enabled
            if self.env['ir.config_parameter'].sudo().get_param('dm.cascade.logging', 'True') == 'True':
                _logger.info(log_entry)
            
        finally:
            self.cascade_in_progress = False
        
        return results
    
    def _get_cascade_rules(self):
        """
        Get CASCADE rules for this model.
        To be overridden by implementing models.
        
        Returns:
            dict: CASCADE rules by trigger field
        """
        return {}
    
    def _apply_cascade_rule(self, rule, old_value, new_value, context=None):
        """
        Apply a single CASCADE rule.
        
        Args:
            rule: Rule definition dict
            old_value: Previous value
            new_value: New value
            context: Additional context
        
        Returns:
            dict: Rule application result
        """
        rule_type = rule.get('type')
        target_field = rule.get('target_field')
        target_model = rule.get('target_model')
        
        if rule_type == 'date':
            return self._cascade_date(rule, old_value, new_value)
        elif rule_type == 'quantity':
            return self._cascade_quantity(rule, old_value, new_value)
        elif rule_type == 'state':
            return self._cascade_state(rule, old_value, new_value)
        else:
            _logger.warning(f"Unknown CASCADE rule type: {rule_type}")
            return None
    
    def _cascade_date(self, rule, old_date, new_date):
        """
        CASCADE date changes according to business rules.
        
        Implements three-layer date CASCADE:
        1. Requested → Planned (with buffer)
        2. Planned → Actual (when executed)
        3. Actual → Updates dependent dates
        """
        if not new_date:
            return None
        
        target_field = rule.get('target_field')
        buffer_days = rule.get('buffer_days', 0)
        
        # Calculate new target date
        if isinstance(new_date, str):
            new_date = fields.Date.from_string(new_date)
        
        target_date = new_date + timedelta(days=buffer_days)
        
        # Apply to target field
        if hasattr(self, target_field):
            self.write({target_field: target_date})
            return {
                'field': target_field,
                'old_value': old_date,
                'new_value': target_date
            }
        
        return None
    
    def _cascade_quantity(self, rule, old_qty, new_qty):
        """
        CASCADE quantity changes (e.g., production → shipment).
        
        Per Appendix Section 5.2: Quantity CASCADE
        """
        target_model = rule.get('target_model')
        target_field = rule.get('target_field')
        link_field = rule.get('link_field')
        
        if not all([target_model, target_field, link_field]):
            return None
        
        # Find related records
        related_records = self.env[target_model].search([
            (link_field, '=', self.id)
        ])
        
        for record in related_records:
            # Apply quantity change
            if hasattr(record, target_field):
                # Calculate proportional change if needed
                if rule.get('proportional', False) and old_qty:
                    ratio = new_qty / old_qty
                    current_value = getattr(record, target_field)
                    new_value = current_value * ratio
                else:
                    new_value = new_qty
                
                record.write({target_field: new_value})
        
        return {
            'model': target_model,
            'records': len(related_records),
            'field': target_field,
            'value': new_qty
        }
    
    def _cascade_state(self, rule, old_state, new_state):
        """
        CASCADE state changes (especially for cancellations).
        
        Per Appendix Section 5.3: State CASCADE on Cancellation
        """
        if new_state != 'cancelled':
            return None
        
        target_model = rule.get('target_model')
        link_field = rule.get('link_field')
        
        # Find related records
        related_records = self.env[target_model].search([
            (link_field, '=', self.id),
            ('state', 'not in', ['done', 'cancelled'])
        ])
        
        for record in related_records:
            # Check if record can be cancelled
            if hasattr(record, 'action_cancel'):
                record.action_cancel()
            else:
                record.write({'state': 'cancelled'})
        
        return {
            'model': target_model,
            'records': len(related_records),
            'action': 'cancelled'
        }
    
    @api.model
    def _check_cascade_consistency(self):
        """
        Validate CASCADE consistency across related records.
        Called periodically or manually for audit.
        """
        inconsistencies = []
        
        # To be implemented by specific models
        # Example: Check if all dates align properly
        
        return inconsistencies