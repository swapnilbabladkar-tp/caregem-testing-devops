class FieldValidationError(Exception):
    pass


class InvalidNewUserError(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg

    def __str__(self):
        return repr(self.code, self.msg)


class DataValidation:
    def __init__(self, values):
        self.values = values

    def validate_required_field(self, fields):
        """
        Validates required fields passed as input
        """
        for field in fields:
            if not self.values.get(field):
                raise FieldValidationError("The field '" + field + "'  is required.")

    def empty_public_method(self):
        pass


class OrganizationLimitError(Exception):
    def __init__(self, message, code):
        self.message = message
        self.code = code
