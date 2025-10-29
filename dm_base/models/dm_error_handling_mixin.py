from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import functools
import logging

_logger = logging.getLogger(__name__)


class DmErrorHandlingMixin(models.AbstractModel):
    """
    Error handling mixin with user-friendly messages.
    
    Per Appendix Section 9: Error Handling Patterns
    """
    _name = 'dm.error.handling.mixin'
    _description = 'DonnaMello Error Handling Mixin'
    
    # Error message catalog
    ERROR_MESSAGES = {
        'DM001': "Cannot allocate {deal_name} to {target_type} - already allocated to {existing}",
        'DM002': "Container utilization ({utilization:.1f}%) is below minimum 65%",
        'DM003': "Incompatible products in same container: {products}",
        'DM004': "Cannot cancel {record_type} in state '{state}'",
        'DM005': "Total lot quantities ({actual:.3f}) don't match ordered quantity ({expected:.3f})",
        'DM006': "Virtual stock imbalance detected for {product}: {quantity:.3f}",
        'DM007': "Cannot load {quantity:.3f} packages - only {available:.3f} produced",
        'DM008': "Price cannot be negative: {field} = {value}",
        'DM009': "Missing required field for {operation}: {field}",
        'DM010': "Date inconsistency: {field1} ({date1}) cannot be after {field2} ({date2})",
        'DM011': "Package quantity must be specified for {product}",
        'DM012': "Cannot modify {field} after {state} state",
        'DM013': "Duplicate {field} value: {value} already exists",
        'DM014': "Invalid {field} format: {value}. Expected format: {format}",
        'DM015': "Insufficient permissions to {operation} {model}",
        'DM016': "Cannot delete {record} - referenced by {references}",
        'DM017': "Weight exceeds container capacity: {weight:.2f} kg > {capacity:.2f} kg",
        'DM018': "Volume exceeds container capacity: {volume:.2f} m³ > {capacity:.2f} m³",
        'DM019': "Cannot allocate - orchestrator validation failed: {reason}",
        'DM020': "Customer PO Number is required and cannot be empty"
    }
    
    def _raise_user_error(self, error_code, **kwargs):
        """
        Raise user-friendly error message.
        
        Args:
            error_code: Error code from ERROR_MESSAGES
            **kwargs: Values to format into error message
        """
        message_template = self.ERROR_MESSAGES.get(
            error_code,
            f"Unknown error occurred (Code: {error_code})"
        )
        
        try:
            message = message_template.format(**kwargs)
        except KeyError as e:
            _logger.error(f"Missing parameter for error {error_code}: {e}")
            message = f"Error {error_code}: {message_template}"
        
        # Log the error
        _logger.error(f"Error {error_code}: {message}")
        
        # Add context if available
        if self:
            message += f"\n\nContext: {self._name} (ID: {self.id})"
        
        raise UserError(message)
    
    def _validate_required_fields(self, fields_list, operation="save"):
        """
        Validate that required fields are present.
        
        Args:
            fields_list: List of field names to check
            operation: Operation being performed
        """
        for field_name in fields_list:
            if not hasattr(self, field_name):
                continue
                
            field = self._fields[field_name]
            value = getattr(self, field_name)
            
            # Check based on field type
            if field.type in ['many2one']:
                if not value:
                    self._raise_user_error('DM009', 
                                         operation=operation,
                                         field=field.string or field_name)
            elif field.type in ['char', 'text']:
                if not value or not value.strip():
                    self._raise_user_error('DM009',
                                         operation=operation,
                                         field=field.string or field_name)
            elif field.type in ['float', 'integer']:
                if value is False or value is None:
                    self._raise_user_error('DM009',
                                         operation=operation,
                                         field=field.string or field_name)
    
    def _validate_positive_values(self, fields_list):
        """
        Validate that numeric fields are positive.
        
        Args:
            fields_list: List of field names to check
        """
        for field_name in fields_list:
            if not hasattr(self, field_name):
                continue
                
            value = getattr(self, field_name)
            field = self._fields[field_name]
            
            if field.type in ['float', 'integer'] and value is not False:
                if value < 0:
                    self._raise_user_error('DM008',
                                         field=field.string or field_name,
                                         value=value)
    
    def _validate_date_sequence(self, date_pairs):
        """
        Validate that dates are in correct sequence.
        
        Args:
            date_pairs: List of tuples (earlier_field, later_field)
        """
        for earlier_field, later_field in date_pairs:
            earlier_date = getattr(self, earlier_field, False)
            later_date = getattr(self, later_field, False)
            
            if earlier_date and later_date and earlier_date > later_date:
                self._raise_user_error('DM010',
                                     field1=self._fields[earlier_field].string,
                                     date1=earlier_date,
                                     field2=self._fields[later_field].string,
                                     date2=later_date)
    
    @api.model
    def safe_unlink(self, check_references=True):
        """
        Safe delete with reference checking.
        
        Args:
            check_references: Whether to check for references
        """
        if check_references:
            # Check for references in common models
            references = []
            
            # To be overridden by specific models
            references = self._get_reference_info()
            
            if references:
                self._raise_user_error('DM016',
                                     record=self.display_name,
                                     references=', '.join(references))
        
        return super().unlink()
    
    def _get_reference_info(self):
        """
        Get information about records referencing this one.
        To be overridden by specific models.
        
        Returns:
            list: List of reference descriptions
        """
        return []


def validate_state_transition(from_states, to_state):
    """
    Decorator to validate state transitions.
    
    Per Appendix Section 9.2: Validation Decorators
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for record in self:
                if hasattr(record, 'state') and record.state not in from_states:
                    if hasattr(record, '_raise_user_error'):
                        record._raise_user_error('DM004',
                                               record_type=record._description or record._name,
                                               state=record.state)
                    else:
                        raise UserError(
                            f"Cannot {func.__name__.replace('_', ' ')} in state '{record.state}'. "
                            f"Operation only allowed from states: {', '.join(from_states)}"
                        )
            
            # Execute the function
            result = func(self, *args, **kwargs)
            
            # Update state if successful
            if to_state:
                self.filtered(lambda r: hasattr(r, 'state')).write({'state': to_state})
            
            return result
        return wrapper
    return decorator


def require_fields(*fields):
    """
    Decorator to require certain fields before operation.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            for record in self:
                if hasattr(record, '_validate_required_fields'):
                    record._validate_required_fields(fields, operation=func.__name__)
                else:
                    for field in fields:
                        if not getattr(record, field, None):
                            raise ValidationError(f"Field '{field}' is required for {func.__name__}")
            return func(self, *args, **kwargs)
        return wrapper
    return decorator