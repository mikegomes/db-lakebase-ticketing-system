import os
import streamlit as st
import psycopg
from psycopg_pool import ConnectionPool
from databricks.sdk import WorkspaceClient

# Page config - MUST be first Streamlit command
st.set_page_config(page_title="Ticketing System", page_icon="🎫", layout="wide")

# Schema name for this app
SCHEMA_NAME = "public"

# Initialize Databricks client for token generation
w = WorkspaceClient()

# Custom connection class that generates fresh OAuth tokens
class OAuthConnection(psycopg.Connection):
    @classmethod
    def connect(cls, conninfo='', **kwargs):
        # Generate a fresh OAuth token for each connection (tokens are workspace-scoped)
        endpoint_name = os.environ["ENDPOINT_NAME"]
        credential = w.postgres.generate_database_credential(endpoint=endpoint_name)
        kwargs['password'] = credential.token
        return super().connect(conninfo, **kwargs)

@st.cache_resource
def get_pool():
    """Create and cache a connection pool with OAuth authentication"""
    # Configure connection parameters
    username = os.environ["PGUSER"]
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    database = os.environ["PGDATABASE"]
    sslmode = os.environ.get("PGSSLMODE", "require")
    
    # Create connection pool with automatic token rotation
    return ConnectionPool(
        conninfo=f"dbname={database} user={username} host={host} port={port} sslmode={sslmode}",
        connection_class=OAuthConnection,
        min_size=1,
        max_size=10,
        open=True
    )

pool = get_pool()

@st.cache_resource
def init_database():
    """Initialize database schema and tables"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
    
            try:
                # Create schema if not exists
                cur.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA_NAME}")
                
                # Create tickets table
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.tickets (
                        ticket_id SERIAL PRIMARY KEY,
                        title VARCHAR(255) NOT NULL,
                        status VARCHAR(50) DEFAULT 'open',
                        created_by VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create ticket_messages table
                cur.execute(f"""
                    CREATE TABLE IF NOT EXISTS {SCHEMA_NAME}.ticket_messages (
                        message_id SERIAL PRIMARY KEY,
                        ticket_id INTEGER REFERENCES {SCHEMA_NAME}.tickets(ticket_id),
                        message_text TEXT NOT NULL,
                        author VARCHAR(255) NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                conn.commit()
            except Exception as e:
                conn.rollback()
                st.error(f"Database initialization error: {e}")

def get_all_tickets():
    """Fetch all tickets from the database"""
    with pool.connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(f"""
                SELECT ticket_id, title, status, created_by, created_at
                FROM {SCHEMA_NAME}.tickets
                ORDER BY created_at DESC
            """)
            return cur.fetchall()

def get_ticket_messages(ticket_id):
    """Fetch all messages for a specific ticket"""
    with pool.connection() as conn:
        with conn.cursor(row_factory=psycopg.rows.dict_row) as cur:
            cur.execute(f"""
                SELECT message_id, message_text, author, created_at
                FROM {SCHEMA_NAME}.ticket_messages
                WHERE ticket_id = %s
                ORDER BY created_at ASC
            """, (ticket_id,))
            return cur.fetchall()

def create_ticket(title, created_by):
    """Create a new ticket"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"""
                    INSERT INTO {SCHEMA_NAME}.tickets (title, created_by)
                    VALUES (%s, %s)
                    RETURNING ticket_id
                """, (title, created_by))
                ticket_id = cur.fetchone()[0]
                conn.commit()
                return ticket_id
            except Exception as e:
                conn.rollback()
                st.error(f"Error creating ticket: {e}")
                return None

def add_message(ticket_id, message_text, author):
    """Add a message to a ticket"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"""
                    INSERT INTO {SCHEMA_NAME}.ticket_messages (ticket_id, message_text, author)
                    VALUES (%s, %s, %s)
                """, (ticket_id, message_text, author))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error adding message: {e}")
                return False

def update_ticket_status(ticket_id, new_status):
    """Update ticket status"""
    with pool.connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(f"""
                    UPDATE {SCHEMA_NAME}.tickets
                    SET status = %s
                    WHERE ticket_id = %s
                """, (new_status, ticket_id))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                st.error(f"Error updating status: {e}")
                return False

# Initialize database
init_database()

# Page header
st.title("🎫 Support Ticketing System")
st.caption("Powered by Databricks & Lakebase")

# Sidebar for ticket list and new ticket creation
with st.sidebar:
    st.header("Tickets")
    
    # New Ticket Form
    with st.expander("➕ Create New Ticket", expanded=False):
        with st.form("new_ticket_form", clear_on_submit=True):
            new_title = st.text_input("Title")
            new_created_by = st.text_input("Your Name")
            submitted = st.form_submit_button("Create Ticket")
            
            if submitted and new_title and new_created_by:
                ticket_id = create_ticket(new_title, new_created_by)
                if ticket_id:
                    st.success(f"Ticket #{ticket_id} created!")
                    st.rerun()
    
    st.divider()
    
    # List all tickets
    tickets = get_all_tickets()
    
    if not tickets:
        st.info("No tickets yet. Create one to get started!")
    else:
        for ticket in tickets:
            status_emoji = "✅" if ticket['status'] == 'closed' else "🔄" if ticket['status'] == 'in_progress' else "🆕"
            if st.button(
                f"{status_emoji} #{ticket['ticket_id']}: {ticket['title'][:30]}...",
                key=f"ticket_{ticket['ticket_id']}",
                use_container_width=True
            ):
                st.session_state.selected_ticket = ticket['ticket_id']

# Main area - Ticket details
if 'selected_ticket' in st.session_state and st.session_state.selected_ticket:
    ticket_id = st.session_state.selected_ticket
    
    # Get ticket details
    tickets = get_all_tickets()
    ticket = next((t for t in tickets if t['ticket_id'] == ticket_id), None)
    
    if ticket:
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.header(f"Ticket #{ticket['ticket_id']}: {ticket['title']}")
        
        with col2:
            # Status update
            new_status = st.selectbox(
                "Status",
                ["open", "in_progress", "closed"],
                index=["open", "in_progress", "closed"].index(ticket['status'] or "open"),
                key=f"status_{ticket_id}"
            )
            if new_status != ticket['status']:
                if update_ticket_status(ticket_id, new_status):
                    st.success("Status updated!")
                    st.rerun()
        
        st.caption(f"Created by {ticket['created_by']} on {ticket['created_at']}")
        st.divider()
        
        # Messages section
        st.subheader("💬 Messages")
        messages = get_ticket_messages(ticket_id)
        
        if messages:
            for msg in messages:
                with st.container():
                    st.markdown(f"**{msg['author']}** - {msg['created_at']}")
                    st.write(msg['message_text'])
                    st.divider()
        else:
            st.info("No messages yet. Be the first to comment!")
        
        # Add message form
        with st.form("add_message_form", clear_on_submit=True):
            st.subheader("Add a Message")
            message_text = st.text_area("Your message")
            message_author = st.text_input("Your name")
            
            if st.form_submit_button("Send Message"):
                if message_text and message_author:
                    if add_message(ticket_id, message_text, message_author):
                        st.success("Message added!")
                        st.rerun()
                else:
                    st.error("Please fill in all fields")
    else:
        st.error("Ticket not found")
else:
    st.info("👈 Select a ticket from the sidebar or create a new one to get started!")
