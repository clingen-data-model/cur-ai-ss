import requests
import streamlit as st

from lib.ui.api import (
    clear_chat,
    get_chat_messages,
    get_http_error_detail,
    send_chat_message_stream,
)


def render_chat_with_agent_tab() -> None:
    paper_resp = st.session_state['paper_resp']

    if 'chat_messages' not in st.session_state:
        st.session_state['chat_messages'] = get_chat_messages(paper_resp.id)

    messages: list[dict[str, str]] = st.session_state['chat_messages']

    for msg in messages:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

    col1, col2 = st.columns([9, 1])
    with col1:
        user_input = st.chat_input('Ask a question about this paper...')
    with col2:
        if st.button('🗑️ Clear', use_container_width=True):
            try:
                clear_chat(paper_resp.id)
                st.session_state['chat_messages'] = []
                st.toast('Chat cleared', icon='🗑️')
                st.rerun()
            except requests.HTTPError as e:
                st.error(get_http_error_detail(e))
            except Exception as e:
                st.error(str(e))

    if user_input:
        messages.append({'role': 'user', 'content': user_input})
        with st.chat_message('user'):
            st.markdown(user_input)
        with st.chat_message('assistant'):
            try:
                response_container = st.empty()
                full_response = ''
                for chunk in send_chat_message_stream(paper_resp.id, user_input):
                    full_response += chunk
                    response_container.markdown(full_response)
                messages.append({'role': 'assistant', 'content': full_response})
            except requests.HTTPError as e:
                st.error(get_http_error_detail(e))
            except Exception as e:
                st.error(str(e))
