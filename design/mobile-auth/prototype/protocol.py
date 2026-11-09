# Prototype Protocol for Human Authorization

from consequence_map.core.canonical import canonical_bytes, proposal_hash

class Authorization:
    def __init__(self):
        self.approvals = {}

    def build_approval_request(self, proposal_id, proposal_content):
        proposal_hash_value = proposal_hash(proposal_content)
        approval_request = {
            'proposal_id': proposal_id,
            'hash': proposal_hash_value,
        }
        return approval_request

    def verify_approval(self, approval_request):
        # Logic to verify the approval request against existing approvals
        pass

# Other necessary functions for handling protocols...