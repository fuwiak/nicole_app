import streamlit as st
import os
from dotenv import load_dotenv
from instagrapi import Client
from groq import Groq

# -----------------------------------------------------------------------------
# Load environment variables
# -----------------------------------------------------------------------------
load_dotenv()
# IG_USERNAME = os.getenv("IG_USERNAME")
# IG_PASSWORD = os.getenv("IG_PASSWORD")

# Accessing API key
# groq_api_key = st.secrets["GROQ_API_KEY"]

# # Accessing Instagram credentials (from a section)
# IG_USERNAME = st.secrets["instagram"]["username"]
# IG_PASSWORD = st.secrets["instagram"]["password"]

# Accessing API key safely
groq_api_key = st.secrets.get("GROQ_API_KEY", None)
if not groq_api_key:
    st.error("GROQ_API_KEY is missing. Please add it to Streamlit Secrets.")

# Accessing Instagram credentials safely
IG_USERNAME = st.secrets.get("instagram", {}).get("username", None)
IG_PASSWORD = st.secrets.get("instagram", {}).get("password", None)


st.write("Secrets loaded successfully! (But not displaying them for security reasons.)")


# -----------------------------------------------------------------------------
# Login to Instagram with instagrapi
# -----------------------------------------------------------------------------
def login_instagram() -> Client:
    """
    Logs into Instagram using instagrapi and returns the authenticated client.
    """
    if not IG_USERNAME or not IG_PASSWORD:
        raise ValueError("Instagram credentials not found in environment variables.")
    
    cl = Client()
    cl.login(IG_USERNAME, IG_PASSWORD)
    return cl

# -----------------------------------------------------------------------------
# Fetch Instagram posts (with images) using instagrapi
# -----------------------------------------------------------------------------
def fetch_user_posts(username: str, count: int = 5):
    """
    Fetch the last 'count' posts of the specified Instagram user.
    Returns a list of dictionaries containing post metadata, including image URLs.
    """
    cl = login_instagram()
    user_id = cl.user_id_from_username(username)
    medias = cl.user_medias(user_id, count)

    posts_data = []
    for media in medias:
        # Convert the HttpUrl / any link to a raw string
        image_url = ""
        if hasattr(media, 'thumbnail_url') and media.thumbnail_url:
            image_url = str(media.thumbnail_url)
        elif hasattr(media, 'resources') and len(media.resources) > 0:
            # Possibly a carousel post; pick first resource's thumbnail_url
            image_url = str(media.resources[0].thumbnail_url)

        posts_data.append({
            "pk": media.pk,
            "caption": media.caption_text,
            "like_count": media.like_count,
            "comment_count": media.comment_count,
            "taken_at": media.taken_at,
            "image_url": image_url,
        })
    return posts_data

# -----------------------------------------------------------------------------
# Use groq to generate a new post in the same style as a selected Instagram post
# -----------------------------------------------------------------------------
def generate_post_in_same_style(post_caption: str) -> str:
    """
    Calls the groq API to generate a new post in the same style as the provided caption.
    """
    client = Groq()

    # We'll create a system instruction and user prompt referencing the caption
    messages = [
        {
            "role": "system",
            "content": (
                "You are an AI specializing in generating short, creative Instagram posts. "
                "Use the style from the user's reference post to influence your tone and theme. "
                "Provide a short caption, 2-5 relevant hashtags, and a recommended posting time."
            )
        },
        {
            "role": "user",
            "content": f"The style of the post is:\n\n{post_caption}\n\nGenerate a new post with a similar style."
        }
    ]

    completion = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=messages,
        temperature=0.6,
        max_completion_tokens=4096,
        top_p=0.95,
        stream=True,
        stop=None,
    )

    final_text = ""
    for chunk in completion:
        piece = chunk.choices[0].delta.content
        if piece:
            final_text += piece

    return final_text.strip()

# -----------------------------------------------------------------------------
# Main Streamlit App
# -----------------------------------------------------------------------------
def main():
    st.title("Instagram Post Style Generator")

    # Make sure we have a place in session_state for certain variables
    if "fetched_posts" not in st.session_state:
        st.session_state.fetched_posts = []
    if "selected_post_pk" not in st.session_state:
        st.session_state.selected_post_pk = None

    st.sidebar.header("Instagram Settings")
    username = st.sidebar.text_input("Instagram username", value="the.mindfuldaily")
    num_posts = st.sidebar.number_input("Number of posts to fetch", min_value=1, max_value=20, value=1)

    # Button to fetch Instagram posts
    # We'll store the results in st.session_state so we don't lose them on rerun
    if st.sidebar.button("Fetch Posts"):
        try:
            with st.spinner(f"Fetching last {num_posts} posts from {username}..."):
                fetched_posts = fetch_user_posts(username, num_posts)
            if not fetched_posts:
                st.sidebar.warning("No posts found or an error occurred.")
                st.session_state.fetched_posts = []
            else:
                st.session_state.fetched_posts = fetched_posts
                st.sidebar.success(f"Fetched {len(fetched_posts)} posts.")
        except Exception as e:
            st.sidebar.error(f"Could not fetch posts. Reason: {e}")
            st.session_state.fetched_posts = []

    # Now display the posts from session_state (if any)
    if st.session_state.fetched_posts:
        st.subheader("Select a post to replicate its style")

        # We'll build the post options with labels and store them in a list
        post_options = []
        for i, post in enumerate(st.session_state.fetched_posts, start=1):
            # We'll build a label for the radio button
            label = f"Post #{i} | Likes: {post['like_count']} | Comments: {post['comment_count']}"
            post_options.append((label, post["pk"]))

        # Convert (label->pk) to a dict so we can retrieve the pk from the selected label
        post_label_to_pk = {label: pk for (label, pk) in post_options}

        # If no item is selected yet, pick the first one as a default
        default_label = list(post_label_to_pk.keys())[0]
        # Current label if we have a saved pk
        current_label = default_label
        # Find label matching st.session_state.selected_post_pk
        for lbl, pk in post_label_to_pk.items():
            if pk == st.session_state.selected_post_pk:
                current_label = lbl
                break

        # A radio with the current selection => 
        selected_label = st.radio(
            "Pick a post's style to replicate",
            options=list(post_label_to_pk.keys()),
            index=list(post_label_to_pk.keys()).index(current_label),
            key="selected_label_radio",
        )

        # Every time the user picks a new label, we update session_state.selected_post_pk
        st.session_state.selected_post_pk = post_label_to_pk[selected_label]

        # Find the corresponding post data for the selection
        selected_post_data = next(
            (p for p in st.session_state.fetched_posts if p["pk"] == st.session_state.selected_post_pk),
            None
        )

        # Show details with an image on the left (or fallback to just URL if there's an error)
        if selected_post_data:
            with st.container():
                col1, col2 = st.columns([1, 3])
                with col1:
                    if selected_post_data["image_url"]:
                        # Attempt to display the image
                        try:
                            st.image(selected_post_data["image_url"], use_column_width=True)
                        except:
                            # If there's any format issue, show the raw URL
                            st.write("Unable to display the image. Here's the URL:")
                            st.write(selected_post_data["image_url"])
                    else:
                        st.write("No image available.")

                with col2:
                    st.write(f"**Caption:** {selected_post_data['caption']}")
                    st.write(f"**Date:** {selected_post_data['taken_at']}")
                    st.write(f"**Likes:** {selected_post_data['like_count']} | **Comments:** {selected_post_data['comment_count']}")

            # Button to generate a similar-style post
            if st.button("Generate Post In Similar Style"):
                with st.spinner("Generating a new post in the same style..."):
                    ai_generated = generate_post_in_same_style(selected_post_data["caption"])
                st.success("AI-Generated Post")
                st.write(ai_generated)
        else:
            st.warning("No post selected yet.")
    else:
        st.write("No posts loaded. Use the sidebar to fetch posts.")


if __name__ == "__main__":
    main()
