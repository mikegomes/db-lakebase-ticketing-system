import os
import uuid
import time
import streamlit as st
import psycopg2
from psycopg2.extras import RealDictCursor
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import GenerateDatabaseCredentialsRequest
from datetime import datetime

# Initialize Databricks client
w = WorkspaceClient()

# Database connection parameters from environment
PGHOST = os.environ["PGHOST"]
PGDATABASE = os.environ["PGDATABASE"]
PGUSER = os.environ["PGUSER"]
PGPORT = os.environ.get("PGPORT", 5432)
CLIENT_ID = os.environ["DATABRICKS_CLIENT_ID"]

# Schema name for this app
SCHEMA_NAME = "public"

# Global connection state
if 'conn' not in st.session_state:
    st.session_state.conn = None
    st.session_state.last_token_refresh = 0

def get_db_credential():
    """Generate database credential using Databricks SDK"""
    try:
        # Try using the dbsql API
        cred = w.dbsql.generate_database_credential(
            GenerateDatabaseCredentialsRequest(
                request_id=str(uuid.uuid4()),
                instance_names=[PGDATABASE]
            )
        )
        return cred.token
    except Exception as e:
        st.error(f"Failed to generate database credential: {e}")
        # Fallback: check if password is in environment
        if "PGPASSWORD" in os.environ:
            return os.environ["PGPASSWORD"]
        raise

def get_db_connection():
    """Get or refresh database connection with token refresh"""
    current_time = time.time()
    
    # Refresh token every 15 minutes (900 seconds)
    if st.session_state.conn is None or (current_time - st.session_state.last_token_refresh) > 900:
        if st.session_state.conn:
            st.session_state.conn.close()
        
        # Generate new credentials
        password = get_db_credential()
        
        # Create new connection
        st.session_state.conn = psycopg2.connect(
            host=PGHOST,
            database=PGDATABASE,
            user=PGUSER,
            port=PGPORT,
            password=password,
            sslmode="require"
        )
        st.session_state.last_token_refresh = current_time
    
    return st.session_state.conn

def init_database():
    """Initialize database schema and tables"""
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    finally:
        cur.close()

def get_all_tickets():
    """Fetch all tickets from the database"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute(f"""
            SELECT ticket_id, title, status, created_by, created_at
            FROM {SCHEMA_NAME}.tickets
            ORDER BY created_at DESC
        """)
        return cur.fetchall()
    finally:
        cur.close()

def get_ticket_messages(ticket_id):
    """Fetch all messages for a specific ticket"""
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        cur.execute(f"""
            SELECT message_id, message_text, author, created_at
            FROM {SCHEMA_NAME}.ticket_messages
            WHERE ticket_id = %s
            ORDER BY created_at ASC
        """, (ticket_id,))
        return cur.fetchall()
    finally:
        cur.close()

def create_ticket(title, created_by):
    """Create a new ticket"""
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    finally:
        cur.close()

def add_message(ticket_id, message_text, author):
    """Add a message to a ticket"""
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    finally:
        cur.close()

def update_ticket_status(ticket_id, new_status):
    """Update ticket status"""
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    finally:
        cur.close()

@st.cache_resource
def init_database_cached():
    """Initialize database schema and tables (cached)"""
    conn = get_db_connection()
    cur = conn.cursor()
    
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
    finally:
        cur.close()

# Initialize database
init_database_cached()

# Page config
st.set_page_config(page_title="Ticketing System", page_icon="🎫", layout="wide")
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
                index=["open", "in_progress", "closed"].index(ticket['status']),
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
