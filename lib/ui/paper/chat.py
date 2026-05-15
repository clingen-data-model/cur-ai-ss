import requests
import streamlit as st

from lib.ui.api import get_chat_messages, get_http_error_detail, send_chat_message


def render_chat_with_agent_tab() -> None:
    paper_resp = st.session_state['paper_resp']

    if 'chat_messages' not in st.session_state:
        st.session_state['chat_messages'] = get_chat_messages(paper_resp.id)

    messages: list[dict[str, str]] = st.session_state['chat_messages']

    for msg in messages:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

    if user_input := st.chat_input('Ask a question about this paper...'):
        messages.append({'role': 'user', 'content': user_input})
        with st.chat_message('user'):
            st.markdown(user_input)
        with st.chat_message('assistant'):
            with st.spinner('Thinking...'):
                try:
                    response = send_chat_message(paper_resp.id, user_input)
                    st.markdown(response)
                    messages.append({'role': 'assistant', 'content': response})
                except requests.HTTPError as e:
                    st.error(get_http_error_detail(e))
                except Exception as e:
                    st.error(str(e))
