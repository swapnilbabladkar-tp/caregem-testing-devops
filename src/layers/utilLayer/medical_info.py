class MedicalType:
    symptoms = "symptoms"
    laboratory = "laboratory"
    medicines = "medicines"
    vitals = "vitals"
    cardiomems = "cardiomems"
    images = "images"
    care_guidelines = "careguidelines"
    fluid_metrics = "fluidmetrics"
    risk_profile = "riskprofile"
    performance_and_utilization = "performanceandutilization"
    education = "education"

    # IMPORTANT: DO NOT change the order of this list, and DO NOT remove any item.
    # If a new MedicalType is needed, append it to the END of the list.
    # The order is used by the Notification model (medical_data_id column), so changing the order or
    # removing an item might corrupt the table.
    ordered_list = [
        symptoms,
        laboratory,
        medicines,
        vitals,
        cardiomems,
        images,
        care_guidelines,
        fluid_metrics,
        risk_profile,
        performance_and_utilization,
        education,
    ]

    @staticmethod
    def get_size():
        """
        Returns length of the ordered list variable
        """
        return len(MedicalType.ordered_list)

    @staticmethod
    def get_index(medical_type):
        """
        Returns the index of the medical type input in the ordered list
        Returns -1 if it doesnt exist
        """
        return (
            MedicalType.ordered_list.index(medical_type)
            if medical_type in MedicalType.ordered_list
            else -1
        )

    @staticmethod
    def get_symptoms_index():
        """
        Returns index of the "symptoms" medical type in the ordered list
        """
        return MedicalType.ordered_list.index(MedicalType.symptoms)
