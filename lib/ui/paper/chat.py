import requests
import streamlit as st

from lib.ui.api import (
    clear_chat,
    generate_chat_response,
    get_chat_messages,
    get_http_error_detail,
    init_chat_message,
)


def render_chat_with_agent_tab() -> None:
    paper_resp = st.session_state['paper_resp']

    if 'chat_messages' not in st.session_state:
        st.session_state['chat_messages'] = get_chat_messages(paper_resp.id)

    # NOTE: this is a HACK until streamlit
    # https://github.com/streamlit/streamlit/issues/8564#issuecomment-4321649533 is released
    chat_container = st.container(height=650, border=None)
    for msg in st.session_state['chat_messages']:
        with chat_container.chat_message(msg['role']):
            st.markdown(msg['content'])
    if user_input := st.chat_input('Ask a question about this paper...'):
        st.session_state['chat_messages'].append(
            {
                'role': 'user',
                'content': user_input,
            }
        )
        with chat_container.chat_message('user'):
            st.markdown(user_input)
        with chat_container.chat_message('assistant'):
            try:
                with chat_container.spinner('Thinking...'):
                    has_init = any(
                        msg['role'] == 'assistant'
                        for msg in st.session_state['chat_messages']
                    )
                    if not has_init:
                        init_chat_message(paper_resp.id, user_input)
                        messages = get_chat_messages(paper_resp.id)
                    else:
                        messages = generate_chat_response(paper_resp.id)
                st.session_state['chat_messages'] = messages
                if messages:
                    st.markdown(messages[-1]['content'])
            except requests.HTTPError as e:
                st.error(get_http_error_detail(e))
            except Exception as e:
                st.error(str(e))
    if st.button('🗑️ Clear Chat', use_container_width=True):
        try:
            clear_chat(paper_resp.id)
            st.session_state['chat_messages'] = []
            st.toast('Chat cleared', icon='🗑️')
            st.rerun()
        except requests.HTTPError as e:
            st.error(get_http_error_detail(e))
        except Exception as e:
            st.error(str(e))
