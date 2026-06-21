+++
title = "Submit an Ad"
date = "2013-02-09T13:21:01+00:00"
slug = "submit-an-ad"
agency = "Unknown"
brand = "Pr"
[cover]
  image = "/img/2013/02/Screen-Shot-2013-02-09-at-5.18.25-AM.png"
+++

I want my readers to have the opportunity to submit ads they would like discussed on ITA. Fill out the fields below — each one doubles as a submission requirement, so if you can complete the form, you've already included everything needed.

<form name="ad-submission" method="POST" data-netlify="true" netlify-honeypot="bot-field" class="contact-form ad-submit-form">
  <input type="hidden" name="form-name" value="ad-submission">
  <p class="contact-form__hidden">
    <label>Don't fill this out if you're human: <input name="bot-field"></label>
  </p>
  <p>
    <label for="ad-brand">Advertising Brand</label><br>
    <input type="text" id="ad-brand" name="brand" placeholder="e.g. Volvo Trucks" required>
  </p>
  <p>
    <label for="ad-product">Product</label><br>
    <input type="text" id="ad-product" name="product" placeholder="e.g. Volvo FH Series">
  </p>
  <p>
    <label for="ad-agency">Advertising Agency</label><br>
    <input type="text" id="ad-agency" name="agency" placeholder="Name, City, State, and Country" required>
  </p>
  <p>
    <label for="ad-link">Link to the Ad</label><br>
    <input type="url" id="ad-link" name="ad_link" placeholder="YouTube, Vimeo, or article URL" required>
  </p>
  <p>
    <label for="ad-credit">Crediting Information</label><br>
    <textarea id="ad-credit" name="credit" rows="4" placeholder="Director, production company, year, awards — anything you'd like credited"></textarea>
  </p>
  <p>
    <label for="ad-submitter">Your Name or Email <span class="ad-submit-form__optional">(optional)</span></label><br>
    <input type="text" id="ad-submitter" name="submitter" placeholder="In case I have questions about the submission">
  </p>
  <p>
    <button type="submit" class="contact-form__submit">Submit This Ad</button>
  </p>
</form>

