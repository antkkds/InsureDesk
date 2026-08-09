"""InsureDesk — Customer Tools.

LLM-callable tools for customer management.
Returns mock data when no DB session is available.
"""

from __future__ import annotations

from src.tools.base import ToolBase, ToolResult


# ══════════════════════════════════════════════════════════════════
# Tool: find_customer
# ══════════════════════════════════════════════════════════════════

class FindCustomer(ToolBase):
    """Search for customers by name or IC."""

    @property
    def name(self) -> str:
        return "find_customer"

    @property
    def description(self) -> str:
        return "Search for existing customers by name, IC number, or email."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "search_term": {
                    "type": "string",
                    "description": "Name, IC number, or email to search for.",
                },
            },
            "required": ["search_term"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        search_term = kwargs.get("search_term", "")

        # Try DB-backed repository first
        try:
            from src.database.db_manager import get_session
            from src.customers.repository import CustomerRepository
            session = get_session()
            repo = CustomerRepository(session)
            customers = repo.search(search_term)
            session.close()
            return ToolResult(
                success=True,
                data={
                    "customers": [
                        {
                            "id": c.id,
                            "name": c.name,
                            "ic": c.ic_number,
                            "email": c.email,
                            "phone": c.phone,
                        }
                        for c in customers
                    ],
                    "count": len(customers),
                    "search_term": search_term,
                },
            )
        except Exception:
            # Fallback: return empty result with helpful note
            return ToolResult(
                success=True,
                data={
                    "customers": [],
                    "count": 0,
                    "search_term": search_term,
                    "note": "Use create_customer to add a new customer record.",
                },
            )


# ══════════════════════════════════════════════════════════════════
# Tool: create_customer
# ══════════════════════════════════════════════════════════════════

class CreateCustomer(ToolBase):
    """Create a new customer record."""

    @property
    def name(self) -> str:
        return "create_customer"

    @property
    def description(self) -> str:
        return (
            "Create a new customer record with name, IC number, "
            "and contact information."
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Customer full name.",
                },
                "ic": {
                    "type": "string",
                    "description": "Identity card / passport number.",
                },
                "email": {
                    "type": "string",
                    "description": "Email address.",
                    "default": "",
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number.",
                    "default": "",
                },
            },
            "required": ["name", "ic"],
        }

    async def execute(self, **kwargs) -> ToolResult:
        name = kwargs.get("name", "")
        ic = kwargs.get("ic", "")
        email = kwargs.get("email", "")
        phone = kwargs.get("phone", "")

        try:
            from src.database.db_manager import get_session
            from src.customers.repository import CustomerRepository
            from src.database.models import Customer

            session = get_session()
            customer = Customer(
                name=name,
                ic_number=ic,
                email=email,
                phone=phone,
            )
            session.add(customer)
            session.commit()
            session.refresh(customer)
            session.close()

            return ToolResult(
                success=True,
                data={
                    "id": str(customer.id),
                    "name": customer.name,
                    "ic": customer.ic_number,
                    "email": customer.email,
                    "phone": customer.phone,
                },
            )
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Failed to create customer: {e}",
            )


# ══════════════════════════════════════════════════════════════════
# Registration helper
# ══════════════════════════════════════════════════════════════════

def register_all_customer_tools(registry):
    """Register all customer tools in the given registry."""
    tools = [
        FindCustomer(),
        CreateCustomer(),
    ]
    registry.register_all(tools)
    return tools
