/**
 * Ejected from @docusaurus/theme-classic (3.10.x).
 *
 * Only reason for the eject: make `navbar.logo.href` mean exactly what it says.
 *
 * These docs are served by the intellistream-web app under a baseUrl, but the
 * logo has to go back to the main site at "/". Upstream runs the href through
 * useBaseUrl, which rewrites "/" into the baseUrl, so the logo links back into
 * the docs. Handing it to <Link> is no better: Link re-applies baseUrl to both
 * `to` and `href`, and would then client-side route to "/" — a path this SPA
 * has no route for, landing on the Docusaurus 404 instead of the real site.
 *
 * So an explicit logo.href is rendered as a plain anchor: path kept verbatim,
 * real navigation out of this app. Without logo.href, behaviour is unchanged.
 */
import React from 'react';
import Link from '@docusaurus/Link';
import useBaseUrl from '@docusaurus/useBaseUrl';
import useDocusaurusContext from '@docusaurus/useDocusaurusContext';
import {useThemeConfig} from '@docusaurus/theme-common';
import ThemedImage from '@theme/ThemedImage';

function LogoThemedImage({logo, alt, imageClassName}) {
  const sources = {
    light: useBaseUrl(logo.src),
    dark: useBaseUrl(logo.srcDark || logo.src),
  };
  const themedImage = (
    <ThemedImage
      className={logo.className}
      sources={sources}
      height={logo.height}
      width={logo.width}
      alt={alt}
      style={logo.style}
    />
  );
  return imageClassName ? (
    <div className={imageClassName}>{themedImage}</div>
  ) : (
    themedImage
  );
}

export default function Logo(props) {
  const {
    siteConfig: {title},
  } = useDocusaurusContext();
  const {
    navbar: {title: navbarTitle, logo},
  } = useThemeConfig();
  const {imageClassName, titleClassName, ...propsRest} = props;
  // Called unconditionally to satisfy the rules of hooks; used only as fallback.
  const siteRoot = useBaseUrl('/');

  const fallbackAlt = navbarTitle ? '' : title;
  const alt = logo?.alt ?? fallbackAlt;

  const content = (
    <>
      {logo && (
        <LogoThemedImage logo={logo} alt={alt} imageClassName={imageClassName} />
      )}
      {navbarTitle != null && <b className={titleClassName}>{navbarTitle}</b>}
    </>
  );

  if (logo?.href) {
    return (
      <a
        href={logo.href}
        {...propsRest}
        {...(logo.target && {target: logo.target})}>
        {content}
      </a>
    );
  }

  return (
    <Link to={siteRoot} {...propsRest} {...(logo?.target && {target: logo.target})}>
      {content}
    </Link>
  );
}
