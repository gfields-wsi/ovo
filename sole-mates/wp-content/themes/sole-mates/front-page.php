<?php
/**
 * Sole Mates homepage: the catalog is the homepage.
 * Hero + catalog + featured split + shop by type + black CTA.
 * Product images are pulled from WooCommerce, so they work with
 * the demo-data plugin images. No sliders, no new features.
 */
get_header();

$hero_id = function_exists( 'wc_get_product_id_by_sku' ) ? wc_get_product_id_by_sku( 'SM-RUN-001' ) : 0;
$hero_img = $hero_id ? get_the_post_thumbnail_url( $hero_id, 'large' ) : '';
$boot_id = function_exists( 'wc_get_product_id_by_sku' ) ? wc_get_product_id_by_sku( 'SM-BOOT-001' ) : 0;
$boot_img = $boot_id ? get_the_post_thumbnail_url( $boot_id, 'large' ) : '';

$types = array(
  array( 'Boots', 'boots', 'SM-BOOT-001' ),
  array( 'Sandals', 'sandals', 'SM-SAND-001' ),
  array( 'Sneakers', 'sneakers', 'SM-SNEA-001' ),
  array( 'Slippers', 'slippers', 'SM-SLIP-001' ),
  array( 'Runners', 'runners', 'SM-RUN-001' ),
);
?>

<main id="main" class="site-main">
  <section class="sm-hero">
    <div>
      <p class="sm-eyebrow">New &mdash; Velocity Road Runners</p>
      <h1>Shoes for<br>every step.</h1>
      <p>Boots, sandals, sneakers, slippers and runners. Every pair is $1 for this demo, in test mode.</p>
      <div class="sm-hero-actions">
        <a class="button" href="<?php echo esc_url( wc_get_page_permalink( 'shop' ) ); ?>">Shop all shoes</a>
        <a class="button sm-button-outline" href="<?php echo esc_url( add_query_arg( 'product_cat', 'runners', wc_get_page_permalink( 'shop' ) ) ); ?>">Explore runners</a>
      </div>
    </div>
    <div class="sm-hero-media">
      <?php if ( $hero_img ) : ?>
        <img src="<?php echo esc_url( $hero_img ); ?>" alt="Velocity Road Runners, Electric Blue">
      <?php endif; ?>
    </div>
  </section>

  <section class="sm-section">
    <p class="sm-eyebrow">The catalog</p>
    <h2>Shop all shoes.</h2>
    <p class="sm-section-intro">Twelve pairs, five types, one price. Pick a shoe, pick a size, check out for $1.</p>
    <?php echo do_shortcode( '[products limit="12" columns="4" orderby="menu_order" order="ASC"]' ); ?>
  </section>

  <section class="sm-section">
    <div class="sm-split">
      <div>
        <p class="sm-eyebrow">Featured</p>
        <h2>Built for rough trails.</h2>
        <p>Trailhead Waterproof Hiking Boots in chestnut brown. Rugged waterproof leather, grippy lugged soles and ankle support for long trails.</p>
        <p><a class="button" href="<?php echo esc_url( add_query_arg( 'product_cat', 'boots', wc_get_page_permalink( 'shop' ) ) ); ?>">Shop boots</a></p>
      </div>
      <div class="sm-split-media">
        <?php if ( $boot_img ) : ?>
          <img src="<?php echo esc_url( $boot_img ); ?>" alt="Trailhead Waterproof Hiking Boots, Chestnut Brown">
        <?php endif; ?>
      </div>
    </div>
  </section>

  <section class="sm-section">
    <p class="sm-eyebrow">Shop by type</p>
    <h2>Find your pair.</h2>
    <div class="sm-types">
      <?php foreach ( $types as $type ) :
        $pid = function_exists( 'wc_get_product_id_by_sku' ) ? wc_get_product_id_by_sku( $type[2] ) : 0;
        $img = $pid ? get_the_post_thumbnail_url( $pid, 'medium' ) : '';
        $url = add_query_arg( 'product_cat', $type[1], wc_get_page_permalink( 'shop' ) );
      ?>
        <a class="sm-type" href="<?php echo esc_url( $url ); ?>">
          <div class="sm-type-media"><?php if ( $img ) : ?><img src="<?php echo esc_url( $img ); ?>" alt="<?php echo esc_attr( $type[0] ); ?>"><?php endif; ?></div>
          <h3><?php echo esc_html( $type[0] ); ?></h3>
          <span>Explore</span>
        </a>
      <?php endforeach; ?>
    </div>
  </section>

  <section class="sm-cta">
    <h2>Join Sole Mates.</h2>
    <p>Be first to hear about new colourways and sizes. No spam, just shoes.</p>
    <p><a class="button sm-button-white" href="<?php echo esc_url( wc_get_page_permalink( 'shop' ) ); ?>">Shop all shoes</a></p>
  </section>
</main>

<?php get_footer(); ?>
