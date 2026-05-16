import requests
import streamlit as st

from lib.ui.api import (
    clear_chat,
    get_chat_messages,
    get_http_error_detail,
    send_chat_message,
)


def render_chat_with_agent_tab() -> None:
    paper_resp = st.session_state['paper_resp']

    if 'chat_messages' not in st.session_state:
        st.session_state['chat_messages'] = get_chat_messages(paper_resp.id)

    for msg in st.session_state['chat_messages']:
        with st.chat_message(msg['role']):
            st.markdown(msg['content'])

    user_input = st.chat_input('Ask a question about this paper...')
    if st.button('🗑️ Clear'):
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
        st.session_state['chat_messages'].append(
            {
                'role': 'user',
                'content': user_input,
            }
        )

        with st.chat_message('user'):
            st.markdown(user_input)

        with st.chat_message('assistant'):
            try:
                with st.spinner('Thinking...'):
                    messages = send_chat_message(paper_resp.id, user_input)
                st.session_state['chat_messages'] = messages
                if messages:
                    st.markdown(messages[-1]['content'])
            except requests.HTTPError as e:
                st.error(get_http_error_detail(e))
            except Exception as e:
                st.error(str(e))
