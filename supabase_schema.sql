-- ============================================================================
-- Supabase Schema: Multi-User Platform with public.users & Cascade Delete
-- ============================================================================
-- 1. public.users (Synchronized with auth.users, visible in Table Editor)
-- 2. public.conversations (Cascades on delete)
-- 3. public.messages (Cascades on delete)
-- 4. public.shared_documents (Knowledge base registry)
-- ============================================================================

-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- ----------------------------------------------------------------------------
-- 1. Table: public.users
-- Visible directly in Supabase Table Editor.
-- Automatically mirrors auth.users. Deleting a user cascades to all their data!
-- ----------------------------------------------------------------------------
create table if not exists public.users (
    id uuid primary key references auth.users(id) on delete cascade,
    email text not null,
    role text not null default 'member',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists users_email_idx on public.users(email);

-- ----------------------------------------------------------------------------
-- 2. Table: conversations
-- Each conversation belongs to an individual user.
-- ----------------------------------------------------------------------------
create table if not exists public.conversations (
    id uuid primary key default gen_random_uuid(),
    user_id uuid references auth.users(id) on delete cascade not null,
    title text not null default 'New Conversation',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists conversations_user_id_idx on public.conversations(user_id);
create index if not exists conversations_updated_at_idx on public.conversations(updated_at desc);

-- ----------------------------------------------------------------------------
-- 3. Table: messages
-- Individual messages belonging to a conversation and user.
-- ----------------------------------------------------------------------------
create table if not exists public.messages (
    id uuid primary key default gen_random_uuid(),
    conversation_id uuid references public.conversations(id) on delete cascade not null,
    user_id uuid references auth.users(id) on delete cascade not null,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    sources jsonb not null default '[]'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists messages_conversation_id_idx on public.messages(conversation_id);
create index if not exists messages_user_id_idx on public.messages(user_id);
create index if not exists messages_created_at_idx on public.messages(created_at asc);

-- ----------------------------------------------------------------------------
-- 4. Table: shared_documents
-- Global shared Knowledge Base document registry.
-- ----------------------------------------------------------------------------
create table if not exists public.shared_documents (
    id uuid primary key default gen_random_uuid(),
    document_id text not null,
    filename text not null,
    source text not null,
    chunks integer not null default 0,
    pages integer not null default 1,
    file_size_bytes bigint default 0,
    uploaded_by text not null default 'anonymous',
    uploader_id uuid references auth.users(id) on delete cascade,
    status text not null default 'Indexed',
    upload_date timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists shared_documents_filename_idx on public.shared_documents(filename);

-- ----------------------------------------------------------------------------
-- 5. Foreign Key Enforcement: Guarantee ON DELETE CASCADE across all tables
-- ----------------------------------------------------------------------------
alter table public.conversations
    drop constraint if exists conversations_user_id_fkey,
    add constraint conversations_user_id_fkey
    foreign key (user_id) references auth.users(id) on delete cascade;

alter table public.messages
    drop constraint if exists messages_conversation_id_fkey,
    add constraint messages_conversation_id_fkey
    foreign key (conversation_id) references public.conversations(id) on delete cascade;

alter table public.messages
    drop constraint if exists messages_user_id_fkey,
    add constraint messages_user_id_fkey
    foreign key (user_id) references auth.users(id) on delete cascade;

alter table public.shared_documents
    drop constraint if exists shared_documents_uploader_id_fkey,
    add constraint shared_documents_uploader_id_fkey
    foreign key (uploader_id) references auth.users(id) on delete cascade;

-- ----------------------------------------------------------------------------
-- 6. Bi-directional Synchronization Triggers between auth.users and public.users
-- ----------------------------------------------------------------------------

-- Trigger A: When a user is created in auth.users, auto-create in public.users
create or replace function public.handle_new_auth_user()
returns trigger as $$
begin
    insert into public.users (id, email, role, created_at, updated_at)
    values (
        new.id,
        coalesce(new.email, 'unknown@ragai.org'),
        coalesce(new.raw_user_meta_data->>'role', 'member'),
        coalesce(new.created_at, now()),
        now()
    )
    on conflict (id) do update
    set email = excluded.email,
        updated_at = now();
    return new;
end;
$$ language plpgsql security definer;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
    after insert or update on auth.users
    for each row
    execute function public.handle_new_auth_user();

-- Trigger B: When a row is deleted from public.users in Table Editor,
-- also delete the user from auth.users (which cascades to all data)!
create or replace function public.handle_public_user_deleted()
returns trigger as $$
begin
    delete from auth.users where id = old.id;
    return old;
end;
$$ language plpgsql security definer;

drop trigger if exists on_public_user_deleted on public.users;
create trigger on_public_user_deleted
    after delete on public.users
    for each row
    execute function public.handle_public_user_deleted();

-- ----------------------------------------------------------------------------
-- 7. Backfill existing auth.users into public.users
-- ----------------------------------------------------------------------------
insert into public.users (id, email, role, created_at, updated_at)
select
    id,
    coalesce(email, 'user@ragai.org'),
    'member',
    coalesce(created_at, now()),
    now()
from auth.users
on conflict (id) do nothing;

-- ----------------------------------------------------------------------------
-- 8. Row Level Security (RLS)
-- ----------------------------------------------------------------------------
alter table public.users enable row level security;
alter table public.conversations enable row level security;
alter table public.messages enable row level security;
alter table public.shared_documents enable row level security;

-- public.users policies
drop policy if exists "Authenticated users can view users" on public.users;
create policy "Authenticated users can view users"
    on public.users for select
    using (auth.role() = 'authenticated');

drop policy if exists "Users can update their own profile" on public.users;
create policy "Users can update their own profile"
    on public.users for update
    using (auth.uid() = id);

-- conversations policies
drop policy if exists "Users can view their own conversations" on public.conversations;
create policy "Users can view their own conversations"
    on public.conversations for select
    using (auth.uid() = user_id);

drop policy if exists "Users can insert their own conversations" on public.conversations;
create policy "Users can insert their own conversations"
    on public.conversations for insert
    with check (auth.uid() = user_id);

drop policy if exists "Users can update their own conversations" on public.conversations;
create policy "Users can update their own conversations"
    on public.conversations for update
    using (auth.uid() = user_id);

drop policy if exists "Users can delete their own conversations" on public.conversations;
create policy "Users can delete their own conversations"
    on public.conversations for delete
    using (auth.uid() = user_id);

-- messages policies
drop policy if exists "Users can view their own messages" on public.messages;
create policy "Users can view their own messages"
    on public.messages for select
    using (auth.uid() = user_id);

drop policy if exists "Users can insert their own messages" on public.messages;
create policy "Users can insert their own messages"
    on public.messages for insert
    with check (auth.uid() = user_id);

drop policy if exists "Users can delete their own messages" on public.messages;
create policy "Users can delete their own messages"
    on public.messages for delete
    using (auth.uid() = user_id);

-- shared_documents policies
drop policy if exists "Anyone authenticated can view shared documents" on public.shared_documents;
create policy "Anyone authenticated can view shared documents"
    on public.shared_documents for select
    using (auth.role() = 'authenticated' or auth.role() = 'anon');

drop policy if exists "Authenticated users can upload shared documents" on public.shared_documents;
create policy "Authenticated users can upload shared documents"
    on public.shared_documents for insert
    with check (auth.role() = 'authenticated' or auth.role() = 'anon');

drop policy if exists "Uploader or admin can delete shared documents" on public.shared_documents;
create policy "Uploader or admin can delete shared documents"
    on public.shared_documents for delete
    using (auth.uid() = uploader_id or auth.jwt()->>'role' = 'service_role');

-- ----------------------------------------------------------------------------
-- 9. Table & Schema Permissions (Grants to PostgREST roles)
-- ----------------------------------------------------------------------------
grant usage on schema public to postgres, anon, authenticated, service_role;

grant all on table public.users to postgres, anon, authenticated, service_role;
grant all on table public.conversations to postgres, anon, authenticated, service_role;
grant all on table public.messages to postgres, anon, authenticated, service_role;
grant all on table public.shared_documents to postgres, anon, authenticated, service_role;

grant all on all sequences in schema public to postgres, anon, authenticated, service_role;
grant all on all routines in schema public to postgres, anon, authenticated, service_role;

alter default privileges in schema public grant all on tables to postgres, anon, authenticated, service_role;
alter default privileges in schema public grant all on sequences to postgres, anon, authenticated, service_role;
