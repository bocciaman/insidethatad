+++
title = "Contact Me"
description = "Get in touch with A.B. Anwar"
slug = "contact-me"
+++

Have a question, tip, or want to share an ad? Use the form below to reach me directly.

<form
  name="contact"
  method="POST"
  data-netlify="true"
  data-netlify-honeypot="bot-field"
  action="/thank-you/"
>
  <input type="hidden" name="form-name" value="contact" />

  <p style="display:none;">
    <label>Don't fill this out if you're human: <input name="bot-field" /></label>
  </p>

  <p>
    <label for="name"><strong>Name</strong></label><br>
    <input type="text" id="name" name="name" required style="width:100%; padding:8px; margin-top:4px;">
  </p>

  <p>
    <label for="email"><strong>Email</strong></label><br>
    <input type="email" id="email" name="email" required style="width:100%; padding:8px; margin-top:4px;">
  </p>

  <p>
    <label for="subject"><strong>Subject</strong></label><br>
    <input type="text" id="subject" name="subject" required style="width:100%; padding:8px; margin-top:4px;">
  </p>

  <p>
    <label for="message"><strong>Message</strong></label><br>
    <textarea id="message" name="message" rows="6" required style="width:100%; padding:8px; margin-top:4px;"></textarea>
  </p>

  <p>
    <button type="submit" style="background:#c0392b; color:#fff; border:none; padding:10px 24px; font-size:1rem; cursor:pointer; font-weight:bold;">
      Send Message
    </button>
  </p>
</form>
